from myapp.models import AISVesselFiltered
from django.db import connection
from collections import defaultdict, Counter
from datetime import datetime, timedelta

PHASE_MAP = {
    'Postponed': 'Waiting',
    'Anchoring': 'Waiting',
    'Approaching': 'Approaching',
    'Maneuvering': 'Approaching',
    'Berthing': 'Berthing',
    'Departure': 'Departure'  # 👈 Now supported
}

MAX_TRT_GAP_SECONDS = 72 * 3600  # 3 days
MAX_PHASE_HOURS = 72
MAX_PHASE_SECONDS = MAX_PHASE_HOURS * 3600

import logging
logger = logging.getLogger(__name__)

def compute_phase_durations():
    logger.info("🔄 compute_phase_durations() triggered")
    task_start = datetime.now()
    print("🚦 Starting phase duration computation...\n")

    # Group AIS records by ship
    ships_data = defaultdict(list)
    for entry in AISVesselFiltered.objects.all().order_by('mmsi', 'received_at'):
        ships_data[entry.mmsi].append(entry)

    all_phase_entries = []
    ship_completeness = {}  # mmsi → 'RAW_ONLY' | 'PHASED' | 'COMPLETED'

    for mmsi, records in ships_data.items():
        prev_status = None
        start_time = None
        last_end_time = None
        trt_cycle_number = 1
        skip_ship = False
        current_phases = set()

        for i, record in enumerate(records):
            current_status = record.status
            timestamp = record.received_at

            # 🚫 Rule: Skip ships stuck in 1 phase too long
            if prev_status == current_status and start_time:
                if (timestamp - start_time).total_seconds() > MAX_PHASE_SECONDS:
                    print(f"❌ MMSI {mmsi} stuck in '{current_status}' > 72 hrs — skipping")
                    skip_ship = True
                    break

            # 🔀 Rule: New TRT cycle
            if last_end_time and (timestamp - last_end_time).total_seconds() > MAX_TRT_GAP_SECONDS:
                trt_cycle_number += 1
                prev_status = None
                start_time = None

            if prev_status is None:
                prev_status = current_status
                start_time = timestamp
                continue

            if current_status != prev_status:
                end_time = timestamp
                duration_seconds = int((end_time - start_time).total_seconds())
                duration_minutes = round(duration_seconds / 60, 2)
                duration_hours = round(duration_seconds / 3600, 2)
                phase = PHASE_MAP.get(prev_status, prev_status)

                # Cap overly long durations
                if duration_hours > MAX_PHASE_HOURS:
                    duration_hours = MAX_PHASE_HOURS
                    duration_minutes = round(duration_hours * 60, 2)
                    duration_seconds = int(duration_hours * 3600)

                if duration_seconds > 0:
                    print(f"📌 {mmsi} | CYCLE {trt_cycle_number} | PHASE: {phase} | {duration_hours:.2f} hrs")
                    current_phases.add(phase)
                    all_phase_entries.append((
                        mmsi, phase, start_time, end_time,
                        duration_minutes, duration_seconds, duration_hours, trt_cycle_number
                    ))

                prev_status = current_status
                start_time = timestamp
                last_end_time = end_time

        if skip_ship:
            continue

        # ✅ Final (tail) segment
        if start_time and prev_status:
            end_time = records[-1].received_at
            duration_seconds = int((end_time - start_time).total_seconds())
            duration_minutes = round(duration_seconds / 60, 2)
            duration_hours = round(duration_seconds / 3600, 2)
            phase = PHASE_MAP.get(prev_status, prev_status)

            if duration_hours > MAX_PHASE_HOURS:
                duration_hours = MAX_PHASE_HOURS
                duration_minutes = round(duration_hours * 60, 2)
                duration_seconds = int(duration_hours * 3600)

            if duration_seconds > 0:
                print(f"📌 {mmsi} | CYCLE {trt_cycle_number} | TAIL PHASE: {phase} | {duration_hours:.2f} hrs")
                current_phases.add(phase)
                all_phase_entries.append((
                    mmsi, phase, start_time, end_time,
                    duration_minutes, duration_seconds, duration_hours, trt_cycle_number
                ))

        # 🧠 Completeness classification
        if {"Waiting", "Approaching", "Berthing", "Departure"}.issubset(current_phases):
            ship_completeness[mmsi] = "COMPLETED"
        elif {"Waiting", "Approaching", "Berthing"}.issubset(current_phases):
            ship_completeness[mmsi] = "PHASED"
        else:
            ship_completeness[mmsi] = "RAW_ONLY"

    print(f"\n📊 Total phase records: {len(all_phase_entries)}")

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM ship_phase_duration")
        cursor.executemany("""
            INSERT INTO ship_phase_duration (
                mmsi, phase, start_time, end_time,
                duration_minutes, duration_seconds, duration_hours,
                trt_cycle_number
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, all_phase_entries)

    # ✅ Phase summary
    summary = Counter([p for (_, p, *_rest) in all_phase_entries])
    print("📋 Phase Count Summary:")
    for phase, count in summary.items():
        print(f"  • {phase}: {count}")

    # ✅ Completeness summary
    completeness_count = Counter(ship_completeness.values())
    print("\n📦 Ship Completeness Levels:")
    for level, count in completeness_count.items():
        print(f"  • {level}: {count} ships")

    end_time = datetime.now()
    total_duration = (end_time - task_start).total_seconds()
    logger.info(f"✅ Finished compute_phase_durations() in {total_duration:.2f}s at {end_time.strftime('%Y-%m-%d %H:%M:%S')}")