from django.db import connection

def populate_daily_phase_tables():
    print("Populating all daily PPI tables...")

    with connection.cursor() as cursor:
        # 🧹 Clear existing entries
        cursor.execute("DELETE FROM daily_waiting_time")
        cursor.execute("DELETE FROM daily_approaching_time")
        cursor.execute("DELETE FROM daily_berthing_time")
        cursor.execute("DELETE FROM daily_turn_round_time")
        cursor.execute("DELETE FROM daily_phase_time")

        # 1️⃣ Waiting Time = Postponed + Anchoring
        cursor.execute("""
            INSERT INTO daily_waiting_time (mmsi, day, total_hours, total_minutes, total_seconds)
            SELECT 
                mmsi,
                DATE(start_time) AS day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                ROUND(SUM(duration_hours * 60)::numeric, 2) AS total_minutes,
                FLOOR(SUM(duration_hours * 3600))::int AS total_seconds
            FROM ship_phase_duration
            WHERE phase IN ('Postponed', 'Anchoring')
            GROUP BY mmsi, day;
        """)

        # 2️⃣ Approaching Time = Approaching + Maneuvering
        cursor.execute("""
            INSERT INTO daily_approaching_time (mmsi, day, total_hours, total_minutes, total_seconds)
            SELECT 
                mmsi,
                DATE(start_time) AS day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                ROUND(SUM(duration_hours * 60)::numeric, 2) AS total_minutes,
                FLOOR(SUM(duration_hours * 3600))::int AS total_seconds
            FROM ship_phase_duration
            WHERE phase IN ('Approaching', 'Maneuvering')
            GROUP BY mmsi, day;
        """)

        # 3️⃣ Berthing Time = Berthing only
        cursor.execute("""
            INSERT INTO daily_berthing_time (mmsi, day, total_hours, total_minutes, total_seconds)
            SELECT 
                mmsi,
                DATE(start_time) AS day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                ROUND(SUM(duration_hours * 60)::numeric, 2) AS total_minutes,
                FLOOR(SUM(duration_hours * 3600))::int AS total_seconds
            FROM ship_phase_duration
            WHERE phase = 'Berthing'
            GROUP BY mmsi, day;
        """)

        # 4️⃣ Turn Round Time = sum of all relevant phases
        cursor.execute("""
            INSERT INTO daily_turn_round_time (mmsi, day, total_hours, total_minutes, total_seconds)
            SELECT 
                mmsi,
                day,
                ROUND(SUM(hours)::numeric, 2) AS total_hours,
                ROUND(SUM(hours * 60)::numeric, 2) AS total_minutes,
                FLOOR(SUM(hours * 3600))::int AS total_seconds
            FROM (
                SELECT 
                    mmsi,
                    DATE(start_time) AS day,
                    duration_hours AS hours
                FROM ship_phase_duration
                WHERE phase IN ('Postponed', 'Anchoring', 'Approaching', 'Maneuvering', 'Berthing')
            ) AS derived
            GROUP BY mmsi, day;
        """)

        # 5️⃣ All Phases (Generic)
        cursor.execute("""
            INSERT INTO daily_phase_time (mmsi, phase, day, total_hours, total_minutes, total_seconds)
            SELECT 
                mmsi,
                phase,
                DATE(start_time) AS day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                ROUND(SUM(duration_hours * 60)::numeric, 2) AS total_minutes,
                FLOOR(SUM(duration_hours * 3600))::int AS total_seconds
            FROM ship_phase_duration
            GROUP BY mmsi, phase, day;
        """)

    print("All daily PPI tables populated with hours, minutes, and seconds!")