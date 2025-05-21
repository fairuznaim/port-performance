from django.db import connection
from collections import defaultdict
from datetime import datetime

PORT_STANDARD_HOURS = {
    "Waiting": 1.0,
    "Approaching": 2.0,
    "Berthing": 18.78,
    "TRT": 21.90
}

def populate_ppi_evaluation():
    print(f"📊 Populating PPI Evaluation Table at {datetime.now()}...\n")

    with connection.cursor() as cursor:
        # Recreate the table
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
                recommendation TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        print("✅ Table recreated.\n")

        def evaluate_phase(value, avg, std):
            if value > std and value > avg:
                return "Too Long"
            elif value < std and value < avg:
                return "Above Standard"
            else:
                return "Right on Time"

        phase_tables = {
            "Waiting": "daily_waiting_time",
            "Approaching": "daily_approaching_time",
            "Berthing": "daily_berthing_time",
            "TRT": "daily_turn_round_time"
        }

        # Collect data
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

        # Calculate averages
        avg_durations = {}
        for phase_name, table_name in phase_tables.items():
            cursor.execute(f"SELECT AVG(total_hours) FROM {table_name}")
            avg = cursor.fetchone()[0] or 0
            avg_durations[phase_name] = avg

        print(f"🧠 Loaded averages: {avg_durations}\n")

        records = []

        print(f"🔍 Processing {len(ship_day_data)} ship-day-cycle records...\n")

        for (mmsi, day, trt_cycle_number), data in ship_day_data.items():
            w = data.get("waiting_hours", 0)
            a = data.get("approaching_hours", 0)
            b = data.get("berthing_hours", 0)
            t = data.get("trt_hours", w + a + b)

            w_status = evaluate_phase(w, avg_durations["Waiting"], PORT_STANDARD_HOURS["Waiting"])
            a_status = evaluate_phase(a, avg_durations["Approaching"], PORT_STANDARD_HOURS["Approaching"])
            b_status = evaluate_phase(b, avg_durations["Berthing"], PORT_STANDARD_HOURS["Berthing"])
            t_status = evaluate_phase(t, avg_durations["TRT"], PORT_STANDARD_HOURS["TRT"])

            too_long_phases = []
            if w_status == "Too Long":
                too_long_phases.append("Waiting")
            if a_status == "Too Long":
                too_long_phases.append("Approaching")
            if b_status == "Too Long":
                too_long_phases.append("Berthing")

            if too_long_phases:
                if len(too_long_phases) == 1:
                    rec = f"Consider optimizing {too_long_phases[0]} procedures."
                elif len(too_long_phases) == 2:
                    rec = f"Consider optimizing {too_long_phases[0]} and {too_long_phases[1]} procedures."
                else:
                    rec = "Consider optimizing Waiting, Approaching, and Berthing procedures."
            elif all(status == "Right on Time" for status in [w_status, a_status, b_status]):
                rec = "Operation meets standard across all phases."
            else:
                rec = "Operation ahead of standards."

            records.append((
                mmsi, day, trt_cycle_number, w, a, b, t,
                w_status, a_status, b_status, t_status,
                rec
            ))

        print(f"✅ Prepared {len(records)} evaluation records.\n")

        # Insert into table
        cursor.executemany("""
            INSERT INTO ppi_evaluation_table (
                mmsi, day, trt_cycle_number,
                waiting_hours, approaching_hours, berthing_hours, trt_hours,
                waiting_status, approaching_status, berthing_status, trt_status,
                recommendation
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, records)

    print(f"🎉 Done! Inserted {len(records)} PPI evaluations at {datetime.now()}.\n")