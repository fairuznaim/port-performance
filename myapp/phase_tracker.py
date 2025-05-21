from myapp.models import AISVesselFiltered
from django.db import connection
from collections import defaultdict, Counter
from datetime import datetime, timedelta

PHASE_MAP = {
    'Postponed': 'Waiting',
    'Anchoring': 'Waiting',
    'Approaching': 'Approaching',
    'Maneuvering': 'Approaching',
    'Berthing': 'Berthing'
}

MAX_TRT_GAP_SECONDS = 72 * 3600  # 3 days
MAX_PHASE_HOURS = 72             # max for all phases
MAX_PHASE_SECONDS = MAX_PHASE_HOURS * 3600

def compute_phase_durations():
    print("🚦 Starting phase duration computation with full control...\n")

    ships_data = defaultdict(list)
    qs = AISVesselFiltered.objects.all().order_by('mmsi', 'received_at')

    for entry in qs:
        ships_data[entry.mmsi].append(entry)

    results = []

    for mmsi, records in ships_data.items():
        prev_status = None
        start_time = None
        last_end_time = None
        trt_cycle_number = 1
        skip_mmsi = False  # ❗ Flag to skip ship if status persists too long

        for i, record in enumerate(records):
            current_status = record.status
            timestamp = record.received_at

            # 🧠 Rule R2: Skip this ship if same status > 3 days
            if prev_status == current_status and start_time:
                if (timestamp - start_time).total_seconds() > MAX_PHASE_SECONDS:
                    print(f"❌ MMSI {mmsi} stuck in status '{current_status}' > 72 hours — skipped entirely")
                    skip_mmsi = True
                    break

            # 🧭 Rule R1: Split TRT cycle if idle gap > 3 days
            if last_end_time and (timestamp - last_end_time).total_seconds() > MAX_TRT_GAP_SECONDS:
                print(f"🔀 New TRT cycle detected for MMSI {mmsi} at {timestamp}")
                trt_cycle_number += 1
                prev_status = None
                start_time = None

            if prev_status is None:
                prev_status = current_status
                start_time = timestamp
                continue

            # 🌀 On status change
            if current_status != prev_status:
                end_time = timestamp
                duration_seconds = int((end_time - start_time).total_seconds())
                duration_minutes = round(duration_seconds / 60, 2)
                duration_hours = round(duration_seconds / 3600, 2)

                phase = PHASE_MAP.get(prev_status, prev_status)

                # ⚖️ Rule R1: Cap all phase durations
                if duration_hours > MAX_PHASE_HOURS:
                    print(f"⚠️ MMSI {mmsi}: {phase} phase too long ({duration_hours:.2f} hrs) — capped.")
                    duration_hours = MAX_PHASE_HOURS
                    duration_minutes = round(duration_hours * 60, 2)
                    duration_seconds = int(duration_hours * 3600)

                if duration_seconds > 0:
                    print(f"📌 MMSI {mmsi} | CYCLE {trt_cycle_number} | STATUS: {prev_status} → PHASE: {phase} | {duration_hours:.2f} hrs")

                    results.append((
                        mmsi,
                        phase,
                        start_time,
                        end_time,
                        duration_minutes,
                        duration_seconds,
                        duration_hours,
                        trt_cycle_number
                    ))

                prev_status = current_status
                start_time = timestamp
                last_end_time = end_time

        # 🚫 Skip if ship was flagged
        if skip_mmsi:
            continue

        # ✅ Final segment (tail)
        if start_time and prev_status:
            end_time = records[-1].received_at
            duration_seconds = int((end_time - start_time).total_seconds())
            duration_minutes = round(duration_seconds / 60, 2)
            duration_hours = round(duration_seconds / 3600, 2)

            phase = PHASE_MAP.get(prev_status, prev_status)

            if duration_hours > MAX_PHASE_HOURS:
                print(f"⚠️ MMSI {mmsi} (tail): {phase} phase too long ({duration_hours:.2f} hrs) — capped.")
                duration_hours = MAX_PHASE_HOURS
                duration_minutes = round(duration_hours * 60, 2)
                duration_seconds = int(duration_hours * 3600)

            if duration_seconds > 0:
                print(f"📌 MMSI {mmsi} | CYCLE {trt_cycle_number} | STATUS: {prev_status} → PHASE: {phase} | {duration_hours:.2f} hrs")

                results.append((
                    mmsi,
                    phase,
                    start_time,
                    end_time,
                    duration_minutes,
                    duration_seconds,
                    duration_hours,
                    trt_cycle_number
                ))

    print(f"\n📊 Total phases to insert: {len(results)}\n")

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM ship_phase_duration")

        insert_sql = """
            INSERT INTO ship_phase_duration (
                mmsi, phase, start_time, end_time,
                duration_minutes, duration_seconds, duration_hours,
                trt_cycle_number
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(insert_sql, results)

    phase_counter = Counter(phase for (_, phase, *_rest) in results)

    print("📋 Phase Summary:")
    for phase, count in phase_counter.items():
        print(f"  • {phase}: {count} entries")

    print("✅ Phase durations successfully inserted into ship_phase_duration.\n")