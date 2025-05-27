from django.db import connection
import logging
logger = logging.getLogger(__name__)
from datetime import datetime

def populate_daily_phase_tables():
    logger.info("📅 populate_daily_phase_tables() triggered")
    start_time = datetime.now()
    logger.info(f"📅 Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("🚢 Populating all daily PPI tables...")

    with connection.cursor() as cursor:
        # 🔄 Clear previous records
        cursor.execute("DELETE FROM daily_waiting_time")
        cursor.execute("DELETE FROM daily_approaching_time")
        cursor.execute("DELETE FROM daily_berthing_time")
        cursor.execute("DELETE FROM daily_turn_round_time")
        cursor.execute("DELETE FROM daily_phase_time")

        # 1️⃣ Daily Waiting Time (Postponed + Anchoring)
        cursor.execute("""
            INSERT INTO daily_waiting_time (mmsi, day, total_hours, trt_cycle_number)
            SELECT 
                mmsi,
                DATE(start_time) AS day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                trt_cycle_number
            FROM ship_phase_duration
            WHERE phase = 'Waiting'
            GROUP BY mmsi, DATE(start_time), trt_cycle_number;
        """)

        # 2️⃣ Daily Approaching Time (Approaching + Maneuvering)
        cursor.execute("""
            INSERT INTO daily_approaching_time (mmsi, day, total_hours, trt_cycle_number)
            SELECT 
                mmsi,
                DATE(start_time) AS day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                trt_cycle_number
            FROM ship_phase_duration
            WHERE phase = 'Approaching'
            GROUP BY mmsi, DATE(start_time), trt_cycle_number;
        """)

        # 3️⃣ Daily Berthing Time
        cursor.execute("""
            INSERT INTO daily_berthing_time (mmsi, day, total_hours, trt_cycle_number)
            SELECT 
                mmsi,
                DATE(start_time) AS day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                trt_cycle_number
            FROM ship_phase_duration
            WHERE phase = 'Berthing'
            GROUP BY mmsi, DATE(start_time), trt_cycle_number;
        """)

        # 4️⃣ Daily Turn Round Time = Waiting + Approaching + Berthing
        cursor.execute("""
            INSERT INTO daily_turn_round_time (mmsi, day, total_hours, trt_cycle_number)
            SELECT
                mmsi,
                day,
                ROUND(SUM(hours)::numeric, 2) AS total_hours,
                trt_cycle_number
            FROM (
                SELECT 
                    mmsi,
                    DATE(start_time) AS day,
                    duration_hours AS hours,
                    trt_cycle_number
                FROM ship_phase_duration
                WHERE phase IN ('Waiting', 'Approaching', 'Berthing')
            ) AS derived
            GROUP BY mmsi, day, trt_cycle_number;
        """)

        # 5️⃣ Daily Phase Time (All phases, diagnostic view)
        cursor.execute("""
            INSERT INTO daily_phase_time (mmsi, phase, day, total_hours, trt_cycle_number)
            SELECT 
                mmsi,
                phase,
                DATE(start_time) AS day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                trt_cycle_number
            FROM ship_phase_duration
            GROUP BY mmsi, phase, DATE(start_time), trt_cycle_number;
        """)

    print("✅ All daily tables populated with trt_cycle_number!")
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    logger.info(f"✅ Finished populate_daily_phase_tables() in {duration:.2f} seconds at {end_time.strftime('%Y-%m-%d %H:%M:%S')}")