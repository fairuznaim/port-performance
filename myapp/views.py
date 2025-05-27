from django.shortcuts import render
from django.http import JsonResponse
from django.db import connection, transaction
from django.views.decorators.csrf import csrf_exempt
from .models import AISData, AISVesselFiltered
from shapely.geometry import Point, Polygon
from collections import defaultdict
from datetime import datetime
from geopy.distance import geodesic
from dateutil import parser
from django.utils.timezone import make_aware
from django.utils.timezone import is_naive, make_aware, localtime
import math, json

from myapp.utils.zone_classifier import classify_ship_status
from myapp.phase_tracker import compute_phase_durations
from myapp.daily_tables import populate_daily_phase_tables
from myapp.ppi_evaluation import populate_ppi_evaluation

PORT_STANDARDS = {
    "waiting": 1.0,
    "approaching": 2.0,
    "berthing": 18.78,
    "turnaround": 21.90
}

DAILY_PHASE_TABLES = {
    'waiting': 'daily_waiting_time',
    'approaching': 'daily_approaching_time',
    'berthing': 'daily_berthing_time',
    'turnaround': 'daily_turn_round_time'
}

# ⚙️ Bearing calculation helper
def calculate_bearing(pointA, pointB):
    lat1, lon1 = map(math.radians, pointA)
    lat2, lon2 = map(math.radians, pointB)
    dlon = lon2 - lon1

    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360

# ✅ Pre-Processing Filtration for AISVesselFiltered

def filter_ais_data_view(request):
    print("🚦 Filtering AISData to populate AISVesselFiltered...")

    port_polygon = Polygon([
        (106.60077079026324, -5.735100186886086),
        (107.0098827822973,  -5.73601089654951),
        (107.00913951802852, -6.162072228756865),
        (106.60002752599446, -6.161161519093441)
    ])
    berthing_target = (-6.100, 106.885)

    ships_qs = AISData.objects.filter(
        lat__isnull=False, lon__isnull=False,
        course__range=(0, 360),
        shiptype__gte=70, shiptype__lte=89,
        shipname__isnull=False, callsign__isnull=False, imo__isnull=False
    ).exclude(shipname='', callsign='')

    ship_groups = defaultdict(list)

    for ship in ships_qs:
        try:
            lat, lon = float(ship.lat), float(ship.lon)
            point = Point(lon, lat)
            if port_polygon.contains(point):
                ship_groups[ship.mmsi].append({
                    "mmsi": ship.mmsi,
                    "lat": lat,
                    "lon": lon,
                    "shiptype": int(ship.shiptype),
                    "speed": float(ship.speed or 0),
                    "received_at": str(ship.received_at),
                    "imo": ship.imo,
                    "callsign": ship.callsign,
                    "shipname": ship.shipname,
                    "status": classify_ship_status(lat, lon, ship.speed or 0),
                    "turn": float(ship.turn or 0),
                    "course": float(ship.course or 0),
                    "heading": float(ship.heading or 0),
                    "to_port": float(ship.to_port or 0),
                    "to_bow": float(ship.to_bow or 0),
                    "to_stern": float(ship.to_stern or 0),
                    "to_starboard": float(ship.to_starboard or 0),
                    "draught": float(ship.draught or 0),
                    "destination": ship.destination or ""
                })
        except Exception as e:
            print(f"⚠️ Error parsing ship: {e}")
            continue

    filtered_ships = []
    for mmsi, points in ship_groups.items():
        if len(points) < 150:
            continue
        try:
            for p in points:
                p["parsed_time"] = parser.parse(p["received_at"])
            sorted_points = sorted(points, key=lambda x: x["parsed_time"])

            # Check continuity
            is_continuous = any(
                abs((sorted_points[i+1]["parsed_time"] - sorted_points[i]["parsed_time"]).total_seconds()) <= 3600 or
                geodesic(
                    (sorted_points[i]["lat"], sorted_points[i]["lon"]),
                    (sorted_points[i+1]["lat"], sorted_points[i+1]["lon"])
                ).nautical <= 12
                for i in range(len(sorted_points) - 1)
            )
            if not is_continuous:
                continue

            # Heading check
            ship_bearing = calculate_bearing(
                (sorted_points[0]["lat"], sorted_points[0]["lon"]),
                (sorted_points[-1]["lat"], sorted_points[-1]["lon"])
            )
            target_bearing = calculate_bearing(
                (sorted_points[-1]["lat"], sorted_points[-1]["lon"]),
                berthing_target
            )
            angle_diff = abs(ship_bearing - target_bearing)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            if angle_diff > 160:
                continue

            for p in sorted_points:
                p["received_at"] = make_aware(p["parsed_time"])
                del p["parsed_time"]
            filtered_ships.extend(sorted_points)
        except Exception as e:
            print(f"⚠️ MMSI {mmsi}: {e}")
            continue

    AISVesselFiltered.objects.all().exclude(mmsi__in=[413338660, 525022130, 357106000]).delete()

    records = [
        AISVesselFiltered(**ship) for ship in filtered_ships
    ]
    AISVesselFiltered.objects.bulk_create(records, batch_size=100)
    print(f"✅ Exported {len(records)} ships to AISVesselFiltered")

    return JsonResponse({"count": len(records)})

# ✅ Map and Data Viewer
from django.utils.timezone import localtime
from django.db.models import Q
from django.utils.timezone import is_naive, make_aware
import json

def map_with_data(request):
    mmsi_filter = request.GET.get("mmsi")
    dates_filter = request.GET.get("dates")

    ships_qs = AISVesselFiltered.objects.all()

    if mmsi_filter:
        ships_qs = ships_qs.filter(mmsi=mmsi_filter)

    if dates_filter:
        selected_dates = dates_filter.split(",")
        ships_qs = ships_qs.filter(
            received_at__date__in=selected_dates
        )

    ships_qs = ships_qs.order_by("mmsi", "received_at")

    # 🔄 Serialize for map
    serialized = []
    for ship in ships_qs:
        received_at = localtime(make_aware(ship.received_at) if is_naive(ship.received_at) else ship.received_at)
        serialized.append({
            "mmsi": ship.mmsi,
            "lat": ship.lat,
            "lon": ship.lon,
            "shiptype": ship.shiptype,
            "speed": ship.speed,
            "received_at": received_at.strftime("%Y-%m-%d %H:%M:%S"),
            "imo": ship.imo,
            "callsign": ship.callsign,
            "shipname": ship.shipname,
            "status": ship.status
        })

    # 📅 Get available dates for calendar filter
    allowed_dates = [
        dt.strftime("%Y-%m-%d")
        for dt in AISVesselFiltered.objects.dates("received_at", "day")
    ]

    return render(request, "index.html", {
        "ships_json": json.dumps(serialized),
        "data": ships_qs,  # for table rendering
        "allowed_dates": json.dumps(allowed_dates),
        "request": request
    })

def get_phase_graph_data(request, phase):
    if phase not in DAILY_PHASE_TABLES:
        return JsonResponse({'error': 'Invalid phase'}, status=400)

    table = DAILY_PHASE_TABLES[phase]
    dates_param = request.GET.get('dates')

    with connection.cursor() as cursor:
        if dates_param:
            selected_dates = dates_param.split(',')
            placeholders = ",".join(["%s"] * len(selected_dates))
            cursor.execute(f"""
                SELECT day, AVG(total_hours) AS avg_hours
                FROM {table}
                WHERE day IN ({placeholders})
                GROUP BY day
                ORDER BY day;
            """, selected_dates)
        else:
            cursor.execute(f"""
                SELECT day, AVG(total_hours) AS avg_hours
                FROM {table}
                GROUP BY day
                ORDER BY day;
            """)

        daily = cursor.fetchall()
        daily_data = [{'date': row[0].strftime('%Y-%m-%d'), 'average': round(row[1], 2)} for row in daily]
        avg_of_avgs = round(sum(d['average'] for d in daily_data) / len(daily_data), 2) if daily_data else 0.0

    return JsonResponse({
        'phase': phase,
        'port_standard': PORT_STANDARDS[phase],
        'overall_average': avg_of_avgs,
        'daily_averages': daily_data
    })


def map_dummy_view(request):
    ships = AISVesselFiltered.objects.filter(
        lat__isnull=False,
        lon__isnull=False,
        shipname__isnull=False,
        callsign__isnull=False,
        imo__isnull=False
    ).exclude(
        shipname='',
        callsign=''
    ).order_by('mmsi', 'received_at')

    serialized = [{
        "mmsi": ship.mmsi,
        "lat": ship.lat,
        "lon": ship.lon,
        "shiptype": ship.shiptype,
        "speed": ship.speed,
        "received_at": localtime(make_aware(ship.received_at) if is_naive(ship.received_at) else ship.received_at).strftime("%Y-%m-%d %H:%M:%S"),
        "imo": ship.imo,
        "callsign": ship.callsign,
        "shipname": ship.shipname,
        "status": ship.status
    } for ship in ships]

    return render(request, "index.html", {
        "ships_json": json.dumps(serialized)
    })


def ppi_dashboard(request):
    mmsi = request.GET.get("mmsi")
    status_filter = request.GET.get("status")
    date_string = request.GET.get("dates")
    selected_dates = []

    query = """
        SELECT mmsi, day, trt_cycle_number,
               waiting_hours, approaching_hours, berthing_hours, trt_hours,
               waiting_status, approaching_status, berthing_status, trt_status,
               recommendation
        FROM ppi_evaluation_table
        WHERE 1=1
    """
    params = []

    if mmsi:
        query += " AND mmsi = %s"
        params.append(mmsi)

    if date_string:
        selected_dates = date_string.split(",")
        placeholders = ",".join(["%s"] * len(selected_dates))
        query += f" AND day IN ({placeholders})"
        params.extend(selected_dates)

    if status_filter:
        query += " AND trt_status = %s"
        params.append(status_filter)

    query += " ORDER BY day DESC, trt_cycle_number LIMIT 500"

    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT day FROM ppi_evaluation_table ORDER BY day")
        available_dates = [row[0].strftime("%Y-%m-%d") for row in cursor.fetchall()]

    return render(request, "ppi_dashboard.html", {
        "records": results,
        "allowed_dates": json.dumps(available_dates),
        "request": request
    })

from django.shortcuts import render
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# Views for rendering pages
def homepage(request):
    return render(request, 'homepage.html')

def index_map(request):
    return render(request, 'index.html')

# Populate Trio Trigger (manual POST refresh)
from myapp.phase_tracker import compute_phase_durations
from myapp.daily_tables import populate_daily_phase_tables
from myapp.ppi_evaluation import populate_ppi_evaluation

@csrf_exempt
def refresh_ppi(request):
    if request.method == 'POST':
        try:
            compute_phase_durations()
            populate_daily_phase_tables()
            populate_ppi_evaluation()
            return JsonResponse({'status': 'success', 'message': 'PPI recalculated!'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)
