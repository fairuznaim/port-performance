from django.db import connection
from collections import defaultdict

# Tanjung Priok Port Standards in Hours
PORT_STANDARD_HOURS = {
    "Waiting": 1.0,
    "Approaching": 2.0,
    "Berthing": 18.78,
    "TRT": 21.90
}

def populate_ppi_evaluation():
    print("📈 Populating PPI Evaluation Table...")

    with connection.cursor() as cursor:
        # Drop if exists and recreate for fresh results
        cursor.execute("DROP TABLE IF EXISTS ppi_evaluation_table")
        cursor.execute("""
            CREATE TABLE ppi_evaluation_table (
                mmsi BIGINT,
                day DATE,
                waiting_hours DOUBLE PRECISION,
                approaching_hours DOUBLE PRECISION,
                berthing_hours DOUBLE PRECISION,
                trt_hours DOUBLE PRECISION,
                waiting_status VARCHAR(64),
                approaching_status VARCHAR(64),
                berthing_status VARCHAR(64),
                trt_status VARCHAR(64),
                recommendation TEXT
            );
        """)

        # Helper function: comparison result
        def evaluate_phase(val, avg, std):
            if val > std and val > avg:
                return "Too Long"
            elif val < std and val < avg:
                return "Above Standard"
            else:
                return "Right on Time"

        # 1️⃣ Fetch daily times per ship
        phase_tables = {
            "Waiting": "daily_waiting_time",
            "Approaching": "daily_approaching_time",
            "Berthing": "daily_berthing_time",
            "TRT": "daily_turn_round_time"
        }

        ship_day_data = defaultdict(lambda: {"mmsi": None, "day": None})

        # Populate per-phase durations
        for phase, table in phase_tables.items():
            cursor.execute(f"SELECT mmsi, day, total_hours FROM {table}")
            for mmsi, day, hours in cursor.fetchall():
                ship_day_data[(mmsi, day)]["mmsi"] = mmsi
                ship_day_data[(mmsi, day)]["day"] = day
                ship_day_data[(mmsi, day)][f"{phase.lower()}_hours"] = hours

        # 2️⃣ Calculate average durations per phase
        avg_durations = {}
        for phase, table in phase_tables.items():
            cursor.execute(f"SELECT AVG(total_hours) FROM {table}")
            avg = cursor.fetchone()[0] or 0
            avg_durations[phase] = avg

        # 3️⃣ Evaluate each ship
        records = []

        for (mmsi, day), data in ship_day_data.items():
            w = data.get("waiting_hours", 0)
            a = data.get("approaching_hours", 0)
            b = data.get("berthing_hours", 0)
            t = data.get("trt_hours", w + a + b)

            w_status = evaluate_phase(w, avg_durations["Waiting"], PORT_STANDARD_HOURS["Waiting"])
            a_status = evaluate_phase(a, avg_durations["Approaching"], PORT_STANDARD_HOURS["Approaching"])
            b_status = evaluate_phase(b, avg_durations["Berthing"], PORT_STANDARD_HOURS["Berthing"])
            t_status = evaluate_phase(t, avg_durations["TRT"], PORT_STANDARD_HOURS["TRT"])

            # 💡 Simple recommendation logic
            if any(s == "Too Long" for s in [w_status, a_status, b_status]):
                rec = "Consider optimizing Waiting/Approaching/Berthing procedures."
            elif all(s == "Right on Time" for s in [w_status, a_status, b_status]):
                rec = "Operation meets standard across all phases."
            else:
                rec = "Operation aheads of standards."

            records.append((
                mmsi, day, w, a, b, t,
                w_status, a_status, b_status, t_status,
                rec
            ))

        # 4️⃣ Insert results
        cursor.executemany("""
            INSERT INTO ppi_evaluation_table (
                mmsi, day,
                waiting_hours, approaching_hours, berthing_hours, trt_hours,
                waiting_status, approaching_status, berthing_status, trt_status,
                recommendation
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, records)

    print(f"✅ Inserted {len(records)} PPI evaluations.")