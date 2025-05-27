from django.db import connection
from collections import defaultdict, Counter
from datetime import datetime

PORT_STANDARD_HOURS = {
    "Waiting": 1.0,
    "Approaching": 2.0,
    "Berthing": 18.78,
    "TRT": 21.90
}

import logging
logger = logging.getLogger(__name__)

def populate_ppi_evaluation():
    logger.info("📊 populate_ppi_evaluation() triggered")
    start_time = datetime.now()
    logger.info(f"📊 Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 Starting PPI Evaluation at {start_time}\n")

    with connection.cursor() as cursor:
        # 💥 Drop and recreate PPI table
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
        print("✅ Table recreated.\n")

        # 1️⃣ Fetch completeness info
        cursor.execute("""
            SELECT mmsi, trt_cycle_number, array_agg(DISTINCT phase)
            FROM ship_phase_duration
            GROUP BY mmsi, trt_cycle_number
        """)
        phase_map = {}  # (mmsi, cycle) → completeness_level
        for mmsi, cycle, phases in cursor.fetchall():
            phase_set = set(phases)
            if {"Waiting", "Approaching", "Berthing", "Departure"}.issubset(phase_set):
                phase_map[(mmsi, cycle)] = "COMPLETED"
            elif {"Waiting", "Approaching", "Berthing"}.issubset(phase_set):
                phase_map[(mmsi, cycle)] = "PHASED"
            else:
                phase_map[(mmsi, cycle)] = "RAW_ONLY"

        # 2️⃣ Phase Aggregation Tables
        phase_tables = {
            "Waiting": "daily_waiting_time",
            "Approaching": "daily_approaching_time",
            "Berthing": "daily_berthing_time",
            "TRT": "daily_turn_round_time"
        }

        # 3️⃣ Load daily durations from all phase tables
        ship_day_data = defaultdict(lambda: {
            "mmsi": None,
            "day": None,
            "trt_cycle_number": None
        })

        for phase_name, table_name in phase_tables.items():
            cursor.execute(f"""
                SELECT mmsi, day, total_hours, trt_cycle_number
                FROM {table_name}
            """)
            for mmsi, day, total_hours, cycle in cursor.fetchall():
                key = (mmsi, day, cycle)
                ship_day_data[key]["mmsi"] = mmsi
                ship_day_data[key]["day"] = day
                ship_day_data[key]["trt_cycle_number"] = cycle
                ship_day_data[key][f"{phase_name.lower()}_hours"] = total_hours

        # 4️⃣ Calculate averages from port
        avg_durations = {}
        for phase_name, table_name in phase_tables.items():
            cursor.execute(f"SELECT AVG(total_hours) FROM {table_name}")
            avg = cursor.fetchone()[0] or 0
            avg_durations[phase_name] = avg

        print(f"🧠 Loaded port-wide averages: {avg_durations}\n")

        def evaluate_phase(value, avg, std):
            if value > std and value > avg:
                return "Too Long"
            elif value < std and value < avg:
                return "Above Standard"
            else:
                return "Right on Time"

        # 5️⃣ Build final records
        records = []
        skipped = 0

        for (mmsi, day, cycle), data in ship_day_data.items():
            completeness = phase_map.get((mmsi, cycle), "RAW_ONLY")

            # ❌ Skip RAW_ONLY ships
            if completeness == "RAW_ONLY":
                skipped += 1
                continue

            w = data.get("waiting_hours", 0)
            a = data.get("approaching_hours", 0)
            b = data.get("berthing_hours", 0)
            t = data.get("trt_hours", w + a + b)

            w_status = evaluate_phase(w, avg_durations["Waiting"], PORT_STANDARD_HOURS["Waiting"])
            a_status = evaluate_phase(a, avg_durations["Approaching"], PORT_STANDARD_HOURS["Approaching"])
            b_status = evaluate_phase(b, avg_durations["Berthing"], PORT_STANDARD_HOURS["Berthing"])
            t_status = evaluate_phase(t, avg_durations["TRT"], PORT_STANDARD_HOURS["TRT"])

            too_long_phases = []
            if w_status == "Too Long": too_long_phases.append("Waiting")
            if a_status == "Too Long": too_long_phases.append("Approaching")
            if b_status == "Too Long": too_long_phases.append("Berthing")

            if too_long_phases:
                rec = f"Consider optimizing {' and '.join(too_long_phases)} procedures."
            elif all(status == "Right on Time" for status in [w_status, a_status, b_status]):
                rec = "Operation meets standard across all phases."
            else:
                rec = "Operation ahead of standards."

            is_partial = (completeness == "PHASED")
            is_completed = (completeness == "COMPLETED")

            records.append((
                mmsi, day, cycle, w, a, b, t,
                w_status, a_status, b_status, t_status,
                is_partial, is_completed,
                rec
            ))

        print(f"✅ Prepared {len(records)} evaluation records ({skipped} raw-only cycles skipped).\n")

        cursor.executemany("""
            INSERT INTO ppi_evaluation_table (
                mmsi, day, trt_cycle_number,
                waiting_hours, approaching_hours, berthing_hours, trt_hours,
                waiting_status, approaching_status, berthing_status, trt_status,
                is_partial, is_completed,
                recommendation
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, records)

    end_time = datetime.now()
    logger.info(f"✅ Finished populate_ppi_evaluation() in {(end_time - start_time).total_seconds():.2f} seconds.")
    print(f"✅ Inserted {len(records)} PPI evaluations at {end_time.strftime('%Y-%m-%d %H:%M:%S')}.\n")