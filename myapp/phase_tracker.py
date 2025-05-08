from myapp.models import AISVesselFiltered
from django.db import connection
from collections import defaultdict, Counter
from datetime import datetime

# 🧠 Normalization Map: status → phase
PHASE_MAP = {
    'Postponed': 'Waiting',
    'Anchoring': 'Waiting',
    'Approaching': 'Approaching',
    'Maneuvering': 'Approaching',
    'Berthing': 'Berthing'
}

def compute_phase_durations():
    print("🚦 Starting phase duration computation...\n")

    ships_data = defaultdict(list)
    qs = AISVesselFiltered.objects.all().order_by('mmsi', 'received_at')

    for entry in qs:
        ships_data[entry.mmsi].append(entry)

    results = []

    for mmsi, records in ships_data.items():
        prev_status = None
        start_time = None

        for record in records:
            current_status = record.status
            timestamp = record.received_at

            if prev_status is None:
                prev_status = current_status
                start_time = timestamp
                continue

            if current_status != prev_status:
                end_time = timestamp
                duration_seconds = int((end_time - start_time).total_seconds())
                duration_minutes = round(duration_seconds / 60, 2)
                duration_hours = round(duration_seconds / 3600, 2)

                if duration_seconds > 0:
                    phase = PHASE_MAP.get(prev_status, prev_status)

                    print(f"📌 MMSI: {mmsi} | STATUS: {prev_status} → PHASE: {phase} | Duration: {duration_hours:.2f} hrs")

                    results.append((
                        mmsi,
                        phase,
                        start_time,
                        end_time,
                        duration_minutes,
                        duration_seconds,
                        duration_hours
                    ))

                prev_status = current_status
                start_time = timestamp

        if start_time and prev_status:
            end_time = records[-1].received_at
            duration_seconds = int((end_time - start_time).total_seconds())
            duration_minutes = round(duration_seconds / 60, 2)
            duration_hours = round(duration_seconds / 3600, 2)

            if duration_seconds > 0:
                phase = PHASE_MAP.get(prev_status, prev_status)

                print(f"📌 MMSI: {mmsi} | STATUS: {prev_status} → PHASE: {phase} | Duration: {duration_hours:.2f} hrs")

                results.append((
                    mmsi,
                    phase,
                    start_time,
                    end_time,
                    duration_minutes,
                    duration_seconds,
                    duration_hours
                ))

    print(f"\n📊 Total phases to insert: {len(results)}\n")

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM ship_phase_duration")

        insert_sql = """
            INSERT INTO ship_phase_duration (
                mmsi, phase, start_time, end_time,
                duration_minutes, duration_seconds, duration_hours
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(insert_sql, results)

    phase_counter = Counter(phase for (_, phase, *_rest) in results)

    print("🕵️ Checking raw statuses in AISVesselFiltered...")
    from django.db.models import Count
    print(dict(AISVesselFiltered.objects.values("status").annotate(count=Count("status"))))


    print("📋 Phase Summary:")
    for phase, count in phase_counter.items():
        print(f"  • {phase}: {count} entries")

    print("✅ Phase durations successfully inserted into ship_phase_duration.")