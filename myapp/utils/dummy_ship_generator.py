from datetime import datetime, timedelta
from myapp.models import AISVesselFiltered
from myapp.utils.zone_classifier import classify_ship_status


def generate_full_dummy_trt_ship():
    print("🚢 Generating full TRT dummy ship...")

    mmsi = 999999999
    imo = 9999999
    callsign = "TEST123"
    shipname = "FULL CYCLE"
    shiptype = 75
    base_time = datetime(2025, 4, 26, 7, 0, 0)

    # Each status block includes: (label, (lat, lon), speed, duration in hours)
    status_blocks = [
        ("Arrival",     (-5.74, 106.85),            6.5, 1),  
        ("Postponed",   (-5.75, 106.85),            0.1, 1),  
        ("Anchoring",   (-5.98, 106.88),            0.4, 2),
        ("Approaching", (-6.05, 106.89),            5.5, 3),
        ("Maneuvering", (-6.097617, 106.88277),     2.5, 1),
        ("Berthing",    (-6.097617, 106.88277),     0.0, 4),
    ]

    entries = []

    for label, (lat, lon), speed, hours in status_blocks:
        steps = int((hours * 60) / 5)  # 5-minute intervals
        for i in range(steps):
            timestamp = base_time + timedelta(minutes=i * 5)
            status = classify_ship_status(lat, lon, speed)

            entries.append(AISVesselFiltered(
                mmsi=mmsi,
                imo=imo,
                callsign=callsign,
                shipname=shipname,
                shiptype=shiptype,
                lat=lat,
                lon=lon,
                speed=speed,
                turn=0,
                course=90,
                heading=90,
                to_port=5,
                to_bow=20,
                to_stern=25,
                to_starboard=5,
                draught=8.0,
                destination="TESTING PORT",
                received_at=timestamp,
                status=status
            ))

        base_time += timedelta(hours=hours)

    # 🧹 Remove old test entries if they exist
    AISVesselFiltered.objects.filter(mmsi=mmsi).delete()
    AISVesselFiltered.objects.bulk_create(entries)

    print(f"✅ Inserted {len(entries)} dummy AIS entries for {shipname}.")