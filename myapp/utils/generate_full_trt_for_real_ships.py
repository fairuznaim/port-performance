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

    # Zone-coherent coordinates
    zones = {
        "Approaching": (-6.05, 106.89),
        "Maneuvering": (-6.097617, 106.88277),
        "Berthing":    (-6.097617, 106.88277),
        "Unberthing":  (-6.097617, 106.88277),
        "Departing":   (-6.00, 106.88),
        "Exit":        (-5.90, 106.86),
    }

    # Each block: label, duration (hrs), speed (knots)
    if mmsi == 525022130:
        phase_blocks = [
            ("Approaching", 3, 6),
            ("Maneuvering", 1, 3),
            ("Berthing",    4, 0),
            ("Unberthing",  1, 2.5),
            ("Departing",   1, 8),
            ("Exit",        1, 12),
        ]
    else:
        phase_blocks = [
            ("Unberthing",  1, 2.5),
            ("Departing",   1, 8),
            ("Exit",        1, 12),
        ]

    for label, hours, speed in phase_blocks:
        lat, lon = zones[label]
        steps = int((hours * 60) / 5)

        for i in range(steps):
            timestamp = start_time + timedelta(minutes=i * 5)
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
    base_times = {
        413338660: datetime(2025, 3, 27, 15, 30, 25) + timedelta(minutes=5),
        525022130: datetime(2025, 3, 29, 15, 9, 21) + timedelta(minutes=5),
        357106000: datetime(2025, 3, 29, 15, 7, 6) + timedelta(minutes=5),
    }

    for mmsi, start_time in base_times.items():
        generate_trt_for_mmsi(mmsi, start_time)