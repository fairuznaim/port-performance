from myapp.models import AISVesselFiltered
from django.db import connection
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from myapp.zone_classifier import classify_ship_status

ALLOWED_STATUSES = {
    "Arrival", "Postponed", "Anchoring",
    "Approaching", "Maneuvering", "Berthing", "Departure"
}

MAX_TRT_GAP_SECONDS = 72 * 3600  # 3 days
MAX_PHASE_HOURS = 72
MAX_PHASE_SECONDS = MAX_PHASE_HOURS * 3600

import logging
logger = logging.getLogger(__name__)


def compute_phase_durations():
    logger.info("compute_phase_durations() triggered")
    task_start = datetime.now()
    print("Starting phase duration computation...\n")

    def normalize_ts(dt):
        return dt.replace(tzinfo=None)

    with connection.cursor() as cursor:
        cursor.execute("SELECT mmsi, phase, start_time, end_time FROM ship_phase_duration")
        existing = set((m, p, normalize_ts(s), normalize_ts(e)) for m, p, s, e in cursor.fetchall())

    ships_data = defaultdict(list)
    for entry in AISVesselFiltered.objects.all().order_by('mmsi', 'received_at'):
        ships_data[entry.mmsi].append(entry)

    all_phase_entries = []
    ship_completeness = {}

    for mmsi, records in ships_data.items():
        prev_phase = None
        start_time = None
        last_end_time = None
        trt_cycle_number = 1
        skip_ship = False
        current_phases = set()
        phase_durations = defaultdict(float)

        for idx, record in enumerate(records):
            lat, lon, speed, timestamp = record.lat, record.lon, record.speed, record.received_at

            new_phase = classify_ship_status(lat, lon, speed, prev_phase)

            if new_phase not in ALLOWED_STATUSES:
                continue

            # Long stuck phase check
            if prev_phase == new_phase and start_time:
                if (timestamp - start_time).total_seconds() > MAX_PHASE_SECONDS:
                    print(f"Skipping MMSI {mmsi}: stuck in '{new_phase}' > 72 hrs")
                    skip_ship = True
                    break

            # TRT cycle split
            if last_end_time and (timestamp - last_end_time).total_seconds() > MAX_TRT_GAP_SECONDS:
                trt_cycle_number += 1
                prev_phase = None
                start_time = None

            if prev_phase is None:
                prev_phase = new_phase
                start_time = timestamp
                continue

            # Phase change logic
            if new_phase != prev_phase:
                end_time = timestamp
                duration_seconds = int((end_time - start_time).total_seconds())
                duration_hours = round(duration_seconds / 3600, 2)
                duration_minutes = round(duration_seconds / 60, 2)

                # Force Departure if transitioning from Berthing to anything else
                if prev_phase == "Berthing" and new_phase != "Berthing":
                    phase = "Departure"
                    print(f"[DEPARTURE] MMSI {mmsi} → Berthing → {new_phase} @ {timestamp}")
                else:
                    phase = prev_phase

                if phase not in ALLOWED_STATUSES:
                    prev_phase = new_phase
                    start_time = timestamp
                    continue

                if duration_hours > MAX_PHASE_HOURS:
                    duration_hours = MAX_PHASE_HOURS
                    duration_minutes = round(duration_hours * 60, 2)
                    duration_seconds = int(duration_hours * 3600)

                key = (mmsi, phase, normalize_ts(start_time), normalize_ts(end_time))

                if duration_seconds > 0 and key not in existing:
                    print(f"{mmsi} | CYCLE {trt_cycle_number} | PHASE: {phase} | {duration_hours:.2f} hrs")
                    all_phase_entries.append((
                        mmsi, phase, start_time, end_time,
                        duration_minutes, duration_seconds, duration_hours, trt_cycle_number
                    ))
                    current_phases.add(phase)
                    if phase in {"Postponed", "Anchoring"}:
                        phase_durations["Waiting"] += duration_hours
                    elif phase in {"Approaching", "Maneuvering"}:
                        phase_durations["Approaching"] += duration_hours
                    elif phase == "Berthing":
                        phase_durations["Berthing"] += duration_hours
                elif duration_seconds == 0:
                    print(f"{mmsi} | PHASE {phase} had zero duration from {start_time} to {end_time}")
                elif key in existing:
                    print(f"{mmsi} | Duplicate phase found — skipping")

                prev_phase = new_phase
                start_time = timestamp
                last_end_time = end_time

        if skip_ship:
            continue

        # Final tail segment
        if start_time and prev_phase:
            end_time = records[-1].received_at
            duration_seconds = int((end_time - start_time).total_seconds())
            duration_hours = round(duration_seconds / 3600, 2)
            duration_minutes = round(duration_seconds / 60, 2)
            phase = prev_phase

            if phase not in ALLOWED_STATUSES:
                continue

            key = (mmsi, phase, normalize_ts(start_time), normalize_ts(end_time))

            if duration_hours > MAX_PHASE_HOURS:
                duration_hours = MAX_PHASE_HOURS
                duration_minutes = round(duration_hours * 60, 2)
                duration_seconds = int(duration_hours * 3600)

            if duration_seconds > 0 and key not in existing:
                print(f"{mmsi} | CYCLE {trt_cycle_number} | TAIL PHASE: {phase} | {duration_hours:.2f} hrs")
                all_phase_entries.append((
                    mmsi, phase, start_time, end_time,
                    duration_minutes, duration_seconds, duration_hours, trt_cycle_number
                ))
                current_phases.add(phase)
                if phase in {"Postponed", "Anchoring"}:
                    phase_durations["Waiting"] += duration_hours
                elif phase in {"Approaching", "Maneuvering"}:
                    phase_durations["Approaching"] += duration_hours
                elif phase == "Berthing":
                    phase_durations["Berthing"] += duration_hours
            elif duration_seconds == 0:
                print(f"{mmsi} | FINAL PHASE {phase} had zero duration — skipped")
            elif key in existing:
                print(f"{mmsi} | Tail duplicate phase skipped")

        # Phase completeness tagging (requires >0h duration)
        if (
            {"Postponed", "Anchoring", "Approaching", "Maneuvering", "Berthing", "Departure"}.intersection(current_phases) and
            all(phase_durations[p] > 0 for p in ["Waiting", "Approaching", "Berthing"])
        ):
            ship_completeness[mmsi] = "COMPLETED"
        elif (
            {"Postponed", "Anchoring", "Approaching", "Maneuvering", "Berthing"}.intersection(current_phases) and
            all(phase_durations[p] > 0 for p in ["Waiting", "Approaching", "Berthing"])
        ):
            ship_completeness[mmsi] = "PHASED"
        else:
            ship_completeness[mmsi] = "RAW_ONLY"

        print(f"{mmsi}: Valid statuses = {sorted(current_phases)} → Completeness = {ship_completeness[mmsi]}")

    print(f"\nTotal new phase entries to insert: {len(all_phase_entries)}")

    if all_phase_entries:
        with connection.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO ship_phase_duration (
                    mmsi, phase, start_time, end_time,
                    duration_minutes, duration_seconds, duration_hours,
                    trt_cycle_number
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, all_phase_entries)

    summary = Counter([p for (_, p, *_rest) in all_phase_entries])
    print("Phase Count Summary:")
    for phase, count in summary.items():
        print(f"  • {phase}: {count}")

    completeness_count = Counter(ship_completeness.values())
    print("\nShip Completeness Levels:")
    for level, count in completeness_count.items():
        print(f"  • {level}: {count} ships")

    duration = (datetime.now() - task_start).total_seconds()
    logger.info(f"Finished compute_phase_durations() in {duration:.2f} seconds")