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
from datetime import datetime, timedelta
from django.db.models import Q
from django.db.models import Func, F, Value, DateTimeField, ExpressionWrapper
from pytz import timezone
from django.db.models.functions import Length
import pytz
import math, json

from myapp.zone_classifier import classify_ship_status
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

# Bearing Calculation
def calculate_bearing(pointA, pointB):
    lat1, lon1 = map(math.radians, pointA)
    lat2, lon2 = map(math.radians, pointB)
    dlon = lon2 - lon1

    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360

# Pre-Processing Filtration for AISVesselFiltered

def filter_ais_data_view(request):
    print("Filtering AISData to populate AISVesselFiltered...")

    port_polygon = Polygon([
        (106.60077079026324, -5.735100186886086),
        (107.0098827822973,  -5.73601089654951),
        (107.00913951802852, -6.162072228756865),
        (106.60002752599446, -6.161161519093441)
    ])
    berthing_target = (-6.100, 106.885)

    from django.db.models import CharField
    from django.db.models.functions import Cast, Length

    ships_qs = AISData.objects.annotate(
        mmsi_str=Cast('mmsi', CharField()),
        mmsi_length=Length(Cast('mmsi', CharField()))
    ).filter(
        mmsi_length=9,
        lat__isnull=False,
        lon__isnull=False,
        course__range=(0, 360),
        shiptype__gte=70,
        shiptype__lte=89,
        shipname__isnull=False,
        callsign__isnull=False,
        imo__isnull=False
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
    print(f"Exported {len(records)} ships to AISVesselFiltered")

    return JsonResponse({"count": len(records)})

# Map and Data Viewer
import json
import pytz
from django.utils.timezone import localtime
from datetime import datetime, timedelta
from django.db.models import Q
from pytz import timezone
from django.utils.timezone import is_naive, make_aware
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils.timezone import make_aware, is_naive, localtime
from django.db.models import Func, F, Value, DateTimeField, ExpressionWrapper
from .models import AISVesselFiltered

def map_with_data(request):
    mmsi_filter = request.GET.get("mmsi")
    dates_filter = request.GET.get("dates")

    # Start with filtered queryset
    from django.db.models import Subquery

    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT mmsi FROM ppi_evaluation_table")
        result = cursor.fetchall()

    ppi_mmsi_list = [row[0] for row in result]
    filtered_qs = AISVesselFiltered.objects.filter(mmsi__in=ppi_mmsi_list)

    if mmsi_filter:
        filtered_qs = filtered_qs.filter(mmsi=mmsi_filter)

    from django.db.models import F, Func, ExpressionWrapper, DateTimeField
    from django.db.models.functions import Cast
    from datetime import datetime
    from pytz import timezone, UTC
    from django.db.models.functions import TruncDate
    from django.utils.timezone import get_fixed_timezone
    import pytz

    jakarta_tz = pytz.timezone('Asia/Jakarta')

    if dates_filter:
        selected_dates = [d.strip() for d in dates_filter.split(",") if d.strip()]
        filtered_qs = filtered_qs.annotate(
            local_day=TruncDate('received_at', tzinfo=jakarta_tz)
        ).filter(local_day__in=selected_dates)
         
        filtered_qs = filtered_qs.order_by('mmsi', 'received_at')

    # Map: serialize ALL ships (filtered)
    serialized = []
    for ship in filtered_qs:
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

    # 📋 Table: paginate the same queryset
    paginator = Paginator(filtered_qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # 📅 Calendar: available date list
    allowed_dates = [
        dt.strftime("%Y-%m-%d")
        for dt in AISVesselFiltered.objects.dates("received_at", "day")
    ]

    return render(request, "index.html", {
        "ships_json": json.dumps(serialized),  
        "data": page_obj,                      
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

# Populate Pre-Processing and Processing (Manual Refresh Button)
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from myapp.phase_tracker import compute_phase_durations
from myapp.daily_tables import populate_daily_phase_tables
from myapp.ppi_evaluation import populate_ppi_evaluation
from myapp.views import filter_ais_data_view  # Ensure this import points to the correct location

@csrf_exempt
def refresh_ppi(request):
    if request.method == 'POST':
        try:
            from myapp.models import AISData, AISVesselFiltered

            # Step 1: Smart skip — only preprocess if new data exists
            latest_filtered = AISVesselFiltered.objects.order_by('-received_at').first()
            latest_raw = AISData.objects.order_by('-received_at').first()

            if not latest_filtered or (latest_raw and latest_raw.received_at > latest_filtered.received_at):
                print("New data found. Running Preprocessing...")
                filter_ais_data_view(request)
            else:
                print("No new AIS data. Skipping preprocessing...")

            # Step 2: Run phase logic regardless
            print("Calculating Phase Durations...")
            compute_phase_durations()

            print("Populating Daily Phase Tables...")
            populate_daily_phase_tables()

            print("Running PPI Evaluation...")
            populate_ppi_evaluation()

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)