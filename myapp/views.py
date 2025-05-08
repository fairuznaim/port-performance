from django.shortcuts import render
from .models import AISData, AISVesselFiltered 
from shapely.geometry import Point, Polygon
from collections import defaultdict
from datetime import datetime
from geopy.distance import geodesic
from dateutil import parser
import math
import json
from django.utils.timezone import make_aware
from myapp.utils.zone_classifier import classify_ship_status

def calculate_bearing(pointA, pointB):
    lat1, lon1 = map(math.radians, pointA)
    lat2, lon2 = map(math.radians, pointB)
    dlon = lon2 - lon1

    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360

def show_data(request):
    data = AISVesselFiltered.objects.filter(
        lat__isnull=False,
        lon__isnull=False,
        shipname__isnull=False,
        callsign__isnull=False,
        imo__isnull=False
    ).exclude(
        shipname='',
        callsign=''
    ).order_by('-received_at')[:500] # HERE'S HOW MANY LINES SHOW UP ON HOME PAGE TABLE

    return render(request, 'myapp/show_data.html', {'data': data})

def map_view(request):
    print("map_view triggered")

    port_polygon = Polygon([
        (106.60077079026324, -5.735100186886086),
        (107.0098827822973,  -5.73601089654951),
        (107.00913951802852, -6.162072228756865),
        (106.60002752599446, -6.161161519093441)
    ])
    berthing_target = (-6.100, 106.885)

    print("📡 Querying AISData...")
    ships_qs = AISData.objects.filter(
        lat__isnull=False,
        lon__isnull=False,
        course__range=(0, 360),
        shiptype__gte=70,
        shiptype__lte=89,
        shipname__isnull=False,
        callsign__isnull=False,
        imo__isnull=False
    ).exclude(
        shipname='',
        callsign='',
    )

    print(f"Total ships after initial DB filter: {ships_qs.count()}")
    invalid_courses = AISData.objects.exclude(course__range=(0, 360)).count()
    print(f"Invalid course values in DB: {invalid_courses}")

    ship_groups = defaultdict(list)

    for ship in ships_qs:
        try:
            lat = float(ship.lat)
            lon = float(ship.lon)
            point = Point(lon, lat)

            if port_polygon.contains(point):
                ship_groups[ship.mmsi].append({
                    "mmsi": ship.mmsi,
                    "lat": lat,
                    "lon": lon,
                    "shiptype": int(ship.shiptype) if ship.shiptype is not None else None,
                    "speed": float(ship.speed) if ship.speed is not None else 0,
                    "received_at": str(ship.received_at),
                    "imo": ship.imo,
                    "callsign": ship.callsign,
                    "shipname": ship.shipname,
                    "status": classify_ship_status(lat, lon, ship.speed or 0),
                    "turn": float(ship.turn) if ship.turn is not None else 0,
                    "course": float(ship.course) if ship.course is not None else 0,
                    "heading": float(ship.heading) if ship.heading is not None else 0,
                    "to_port": float(ship.to_port) if ship.to_port is not None else 0,
                    "to_bow": float(ship.to_bow) if ship.to_bow is not None else 0,
                    "to_stern": float(ship.to_stern) if ship.to_stern is not None else 0,
                    "to_starboard": float(ship.to_starboard) if ship.to_starboard is not None else 0,
                    "draught": float(ship.draught) if hasattr(ship, 'draught') and ship.draught is not None else 0,
                    "destination": ship.destination or ""
                })

        except Exception as e:
            print(f"Parse Error: {e}")
            continue

    print(f"Ships inside port polygon: {sum(len(v) for v in ship_groups.values())}")
    print(f"MMSI groups formed: {len(ship_groups)}")

    filtered_ships = []

    for mmsi, points in ship_groups.items():
        if len(points) < 150:
            continue

        try:
            for p in points:
                p["parsed_time"] = parser.parse(p["received_at"])

            sorted_points = sorted(points, key=lambda x: x["parsed_time"])

            is_continuous = False
            for i in range(len(sorted_points) - 1):
                t1 = sorted_points[i]["parsed_time"]
                t2 = sorted_points[i + 1]["parsed_time"]
                delta_t = abs((t2 - t1).total_seconds())

                loc1 = (sorted_points[i]["lat"], sorted_points[i]["lon"])
                loc2 = (sorted_points[i + 1]["lat"], sorted_points[i + 1]["lon"])
                delta_d = geodesic(loc1, loc2).nautical

                if delta_t <= 3600 or delta_d <= 12:
                    is_continuous = True
                    break

            if not is_continuous:
                continue

            start_point = (sorted_points[0]["lat"], sorted_points[0]["lon"])
            end_point = (sorted_points[-1]["lat"], sorted_points[-1]["lon"])

            ship_bearing = calculate_bearing(start_point, end_point)
            target_bearing = calculate_bearing(end_point, berthing_target)

            angle_diff = abs(ship_bearing - target_bearing)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff

            print(f"[{mmsi}] Ship → {ship_bearing:.1f}°, Target → {target_bearing:.1f}°, Δ: {angle_diff:.1f}°")

            if angle_diff > 160:
                continue

            for p in sorted_points:
                p["received_at"] = make_aware(p["parsed_time"])
                del p["parsed_time"]

            filtered_ships.extend(sorted_points)

        except Exception as e:
            print(f"[{mmsi}] ⚠️ Error during filtering: {e}")
            continue

    print(f"✅ Final Filtered Ships: {len(filtered_ships)}")

    # 🚢 Export to DB
    AISVesselFiltered.objects.all().delete()

    if filtered_ships:
        records = [
            AISVesselFiltered(
                mmsi=ship.get("mmsi"),
                received_at=ship.get("received_at"),
                status=ship.get("status"),
                turn=ship.get("turn"),
                speed=ship.get("speed"),
                lat=ship.get("lat"),
                lon=ship.get("lon"),
                course=ship.get("course"),
                heading=ship.get("heading"),
                imo=ship.get("imo"),
                callsign=ship.get("callsign"),
                shipname=ship.get("shipname"),
                shiptype=ship.get("shiptype"),
                to_port=ship.get("to_port"),
                to_bow=ship.get("to_bow"),
                to_stern=ship.get("to_stern"),
                to_starboard=ship.get("to_starboard"),
                draught=ship.get("draught"),
                destination=ship.get("destination")
            ) for ship in filtered_ships
        ]
        AISVesselFiltered.objects.bulk_create(records, batch_size=100)
        print(f"Exported {len(records)} ships to ais_vessel_filtered")

        from myapp.phase_tracker import compute_phase_durations
        compute_phase_durations()

    else:
        print("⚠️ No ships passed filtering. Table not updated.")

    # 💡 Format datetimes to strings for safe JSON serialization
    for ship in filtered_ships:
        if isinstance(ship["received_at"], datetime):
            ship["received_at"] = ship["received_at"].strftime("%Y-%m-%d %H:%M:%S")

    # 💾 JSON safety wrapper
    try:
        ships_json = json.dumps(filtered_ships)
    except Exception as e:
        ships_json = "[]"
        print(f"❌ JSON dump failed: {e}")

    return render(request, "myapp/index.html", {
        "ships_json": ships_json
    })