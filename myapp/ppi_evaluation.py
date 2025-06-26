from django.db import connection
from collections import defaultdict
from datetime import datetime

import logging
logger = logging.getLogger(__name__)

PORT_STANDARD_HOURS = {
    "Waiting": 1.0,
    "Approaching": 2.0,
    "Berthing": 18.78,
    "TRT": 21.90
}

def populate_ppi_evaluation():
    logger.info("populate_ppi_evaluation() triggered")
    start_time = datetime.now()
    print(f"\nStarting PPI Evaluation at {start_time}\n")

    with connection.cursor() as cursor:
        # Recreate the evaluation table cleanly
        cursor.execute("DROP TABLE IF EXISTS ppi_evaluation_table CASCADE")
        cursor.execute("""
            CREATE TABLE ppi_evaluation_table (
                mmsi BIGINT,
                day DATE,
                trt_cycle_number INTEGER,
                waiting_hours DOUBLE PRECISION,
                approaching_hours DOUBLE PRECISION,
                berthing_hours DOUBLE PRECISION,
                trt_hours DOUBLE PRECISION,
                waiting_status VARCHAR(64),
                approaching_status VARCHAR(64),
                berthing_status VARCHAR(64),
                trt_status VARCHAR(64),
                is_partial BOOLEAN,
                is_completed BOOLEAN,
                recommendation TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        print("✓ ppi_evaluation_table recreated.\n")

        # Map ship completeness by TRT cycle
        cursor.execute("""
            SELECT mmsi, trt_cycle_number,
                bool_or(phase = 'Waiting' AND duration_hours > 0) as has_waiting,
                bool_or(phase = 'Approaching' AND duration_hours > 0) as has_approaching,
                bool_or(phase = 'Berthing' AND duration_hours > 0) as has_berthing,
                bool_or(phase = 'Departure') as has_departure
            FROM ship_phase_duration
            GROUP BY mmsi, trt_cycle_number
        """)

        phase_map = {}  # (mmsi, cycle) → completeness_level
        for mmsi, cycle, has_waiting, has_approaching, has_berthing, has_departure in cursor.fetchall():
            if has_waiting and has_approaching and has_berthing and has_departure:
                phase_map[(mmsi, cycle)] = "COMPLETED"
            elif has_waiting and has_approaching and has_berthing:
                phase_map[(mmsi, cycle)] = "PHASED"
            else:
                phase_map[(mmsi, cycle)] = "RAW_ONLY"

        # Load durations from daily tables
        phase_tables = {
            "Waiting": "daily_waiting_time",
            "Approaching": "daily_approaching_time",
            "Berthing": "daily_berthing_time",
            "TRT": "daily_turn_round_time"
        }

        ship_day_data = defaultdict(lambda: {
            "mmsi": None,
            "day": None,
            "trt_cycle_number": None
        })

        for phase, table in phase_tables.items():
            cursor.execute(f"""
                SELECT mmsi, day, total_hours, trt_cycle_number
                FROM {table};
            """)
            for mmsi, day, total, cycle in cursor.fetchall():
                key = (mmsi, day, cycle)
                ship_day_data[key]["mmsi"] = mmsi
                ship_day_data[key]["day"] = day
                ship_day_data[key]["trt_cycle_number"] = cycle
                ship_day_data[key][f"{phase.lower()}_hours"] = total

        # Calculate port-wide averages
        avg_durations = {}
        for phase, table in phase_tables.items():
            cursor.execute(f"SELECT AVG(total_hours) FROM {table}")
            avg = cursor.fetchone()[0] or 0
            avg_durations[phase] = round(avg, 2)

        print(f"✓ Loaded Port Averages: {avg_durations}\n")

        # Phase evaluation function
        def evaluate_phase(value, avg, std):
            if value is None or value == 0:
                return "No Data"
            if value > std:
                return "Slower than Standard"
            elif value < std:
                return "Faster than Standard"
            else:
                return "Right on Time"

        records = []
        skipped = 0

        for (mmsi, day, cycle), data in ship_day_data.items():
            completeness = phase_map.get((mmsi, cycle), "RAW_ONLY")
            w = data.get("waiting_hours", 0)
            a = data.get("approaching_hours", 0)
            b = data.get("berthing_hours", 0)
            t = data.get("trt_hours", w + a + b)

            # Skip invalid or incomplete cycles
            if completeness == "RAW_ONLY" or a == 0 or b == 0:
                print(f"Skipping: {mmsi} | {day} | Phase Durations: W:{w}, A:{a}, B:{b} | {completeness}")
                skipped += 1
                continue

            # Evaluate
            w_status = evaluate_phase(w, avg_durations["Waiting"], PORT_STANDARD_HOURS["Waiting"])
            a_status = evaluate_phase(a, avg_durations["Approaching"], PORT_STANDARD_HOURS["Approaching"])
            b_status = evaluate_phase(b, avg_durations["Berthing"], PORT_STANDARD_HOURS["Berthing"])
            t_status = evaluate_phase(t, avg_durations["TRT"], PORT_STANDARD_HOURS["TRT"])

            phase_statuses = {
                "Waiting": w_status,
                "Approaching": a_status,
                "Berthing": b_status
            }

            slower_phases = [phase for phase, status in phase_statuses.items() if status == "Slower than Standard"]
            exact_match = all(status == "Right on Time" for status in phase_statuses.values())
            has_faster = any(status == "Faster than Standard" for status in phase_statuses.values())

            if slower_phases:
                if len(slower_phases) == 1:
                    recommendation = f"Consider optimizing {slower_phases[0]} procedures."
                elif len(slower_phases) == 2:
                    recommendation = f"Consider optimizing {slower_phases[0]} and {slower_phases[1]} procedures."
                else:
                    recommendation = "Consider optimizing Waiting, Approaching, and Berthing procedures."
            elif exact_match:
                recommendation = "Operation meets port standards across all phases."
            elif has_faster:
                recommendation = "Performance exceeds port standards."
            else:
                recommendation = "Performance exceeds port standards."

            is_partial = completeness == "PHASED"
            is_completed = completeness == "COMPLETED"

            records.append((
                mmsi, day, cycle, w, a, b, t,
                w_status, a_status, b_status, t_status,
                is_partial, is_completed,
                recommendation
            ))

        print(f"Prepared {len(records)} PPI records | Skipped {skipped} incomplete cycles.\n")

        # Insert into ppi_evaluation_table
        if records:
            cursor.executemany("""
                INSERT INTO ppi_evaluation_table (
                    mmsi, day, trt_cycle_number,
                    waiting_hours, approaching_hours, berthing_hours, trt_hours,
                    waiting_status, approaching_status, berthing_status, trt_status,
                    is_partial, is_completed, recommendation
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, records)

    logger.info(f"populate_ppi_evaluation() finished with {len(records)} rows inserted.")
    print("Evaluation completed and written to `ppi_evaluation_table`.\n")