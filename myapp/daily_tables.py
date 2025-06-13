from django.db import connection
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def populate_daily_phase_tables():
    logger.info("populate_daily_phase_tables() triggered")
    start_time = datetime.now()
    print("Populating daily PPI tables...")

    with connection.cursor() as cursor:
        # Clear Previous Daily Tables
        cursor.execute("DELETE FROM daily_waiting_time")
        cursor.execute("DELETE FROM daily_approaching_time")
        cursor.execute("DELETE FROM daily_berthing_time")
        cursor.execute("DELETE FROM daily_turn_round_time")
        cursor.execute("DELETE FROM daily_phase_time")

        # Waiting Time: includes Postponed + Anchoring → mapped to 'Waiting'
        cursor.execute("""
            INSERT INTO daily_waiting_time (mmsi, day, total_hours, trt_cycle_number)
            SELECT 
                mmsi,
                DATE(start_time) AS day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                trt_cycle_number
            FROM ship_phase_duration
            WHERE phase = 'Waiting' AND duration_hours > 0
            GROUP BY mmsi, DATE(start_time), trt_cycle_number;
        """)

        # Approaching Time: includes Approaching + Maneuvering → Mapped to 'Approaching'
        cursor.execute("""
            INSERT INTO daily_approaching_time (mmsi, day, total_hours, trt_cycle_number)
            SELECT 
                mmsi,
                DATE(start_time) AS day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                trt_cycle_number
            FROM ship_phase_duration
            WHERE phase = 'Approaching' AND duration_hours > 0
            GROUP BY mmsi, DATE(start_time), trt_cycle_number;
        """)

        # Berthing Time
        cursor.execute("""
            INSERT INTO daily_berthing_time (mmsi, day, total_hours, trt_cycle_number)
            SELECT 
                mmsi,
                DATE(start_time) AS day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                trt_cycle_number
            FROM ship_phase_duration
            WHERE phase = 'Berthing' AND duration_hours > 0
            GROUP BY mmsi, DATE(start_time), trt_cycle_number;
        """)

        # Turn Round Time = Waiting + Approaching + Berthing
        cursor.execute("""
            INSERT INTO daily_turn_round_time (mmsi, day, total_hours, trt_cycle_number)
            SELECT
                mmsi,
                phase_day,
                ROUND(SUM(duration_hours)::numeric, 2) AS total_hours,
                trt_cycle_number
            FROM (
                SELECT 
                    mmsi,
                    DATE(start_time) AS phase_day,
                    duration_hours,
                    trt_cycle_number
                FROM ship_phase_duration
                WHERE phase IN ('Waiting', 'Approaching', 'Berthing')
                AND duration_hours > 0
            ) AS filtered
            GROUP BY mmsi, phase_day, trt_cycle_number;
        """)

        # Diagnostic View: All Phases
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

    end_time = datetime.now()
    print("✅ All daily phase tables populated.")
    logger.info(f"populate_daily_phase_tables() completed in {(end_time - start_time).total_seconds():.2f}s at {end_time.strftime('%Y-%m-%d %H:%M:%S')}")