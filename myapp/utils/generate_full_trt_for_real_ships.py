from datetime import datetime, timedelta
from myapp.models import AISVesselFiltered
from myapp.utils.zone_classifier import classify_ship_status

def generate_trt_for_mmsi(mmsi, start_time):
    print(f"🛠 Generating AIS for MMSI {mmsi}")
    entries = []

    shipname_map = {
        413338660: "ZHONG GU XIA MEN",
        525022130: "KM RIK NO.03",
        357106000: "MSC DIEGO"
    }

    imo_map = {
        413338660: 9810240,
        525022130: 8904874,
        357106000: 9202649
    }

    callsign_map = {
        413338660: "BQIX",
        525022130: "PNVF",
        357106000: "3FZP8"
    }

    shipname = shipname_map[mmsi]
    imo = imo_map[mmsi]
    callsign = callsign_map[mmsi]
    shiptype = 70

    # 📍 Phase locations
    phase_path = {
        "Postponed":   (-5.75, 106.85),
        "Anchoring":   (-5.98, 106.88),
        "Approaching": (-6.04, 106.89),
        "Maneuvering": (-6.0975, 106.8830),
        "Berthing":    (-6.0975, 106.8830),
        "Departing":   (-6.00, 106.88),   # treat as end-of-BERTHING point
    }

    # ⏱ Phase durations + speeds
    phase_blocks = [
        ("Postponed",   4, 0.1),
        ("Anchoring",   6, 0.3),
        ("Approaching", 2, 5.0),
        ("Maneuvering", 1, 2.5),
        ("Berthing",    4, 0.0),
        ("Departing",   2, 8.0),  # 💡 Departure as terminal marker
    ]

    interval_minutes = 2  # Finer resolution

    for label, hours, speed in phase_blocks:
        lat, lon = phase_path[label]
        steps = int((hours * 60) / interval_minutes)

        for i in range(steps):
            timestamp = start_time + timedelta(minutes=i * interval_minutes)
            status = classify_ship_status(lat, lon, speed)

            entry = AISVesselFiltered(
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
                destination="AUTOGEN PORT",
                received_at=timestamp,
                status=status
            )
            entries.append(entry)

        start_time += timedelta(hours=hours)

    AISVesselFiltered.objects.bulk_create(entries)
    print(f"✅ Inserted {len(entries)} points for {shipname} ({mmsi})")


def generate_all_trt_ships():
    mmsi_list = [413338660, 525022130, 357106000]

    for mmsi in mmsi_list:
        latest = AISVesselFiltered.objects.filter(mmsi=mmsi).order_by("-received_at").first()
        base_time = (latest.received_at + timedelta(minutes=5)) if latest else datetime(2025, 3, 27, 8, 0, 0)
        generate_trt_for_mmsi(mmsi, base_time)