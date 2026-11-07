"""Telemetry simulator: stands in for the prosthesis chips sending readings over 4G.

Every INTERVAL_SECONDS it inserts one reading per known prosthesis into the telemetry
database, so the hourly ETL always has fresh data to pick up and the "processed until"
watermark can be demonstrated.
"""
import logging
import os
import random
import time
from datetime import datetime, timezone

import psycopg2

DSN = os.environ["TELEMETRY_DSN"]
INTERVAL = float(os.environ.get("INTERVAL_SECONDS", "10"))
PROSTHESES = {  # serial -> typical reaction time, ms
    "BP-ARM-2024-0001": 78,
    "BP-ARM-2024-0002": 92,
    "BP-HND-2025-0003": 70,
    "BP-ARM-2025-0004": 64,
}
GESTURES = ["grip", "release", "pinch", "point", "rotate", "rest"]
ERRORS = ["ACT_OVERCURRENT", "BMS_OVERHEAT", "SENSOR_DROPOUT"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def reading(serial: str, base_ms: int, now: datetime) -> tuple:
    gesture = random.choice(GESTURES)
    reaction = int(max(35, min(260, base_ms + random.uniform(-30, 30) + (90 if random.random() < 0.08 else 0))))
    noise = round(random.uniform(0.05, 0.35), 3)
    battery = max(5, 100 - int(now.timestamp() // 180 % 480) // 5)
    error = random.choice(ERRORS) if random.random() < 0.004 else None
    return serial, now, gesture, reaction, noise, battery, error


def connect():
    while True:
        try:
            conn = psycopg2.connect(DSN)
            conn.autocommit = True
            return conn
        except psycopg2.OperationalError as exc:
            logging.warning("telemetry db not ready: %s", exc)
            time.sleep(3)


def main() -> None:
    conn = connect()
    logging.info("simulating %d prostheses every %.0fs", len(PROSTHESES), INTERVAL)
    while True:
        now = datetime.now(timezone.utc)
        rows = [reading(s, ms, now) for s, ms in PROSTHESES.items()]
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO telemetry (prosthesis_serial, recorded_at, gesture, reaction_ms, "
                    "myo_noise_level, battery_pct, error_code) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    rows,
                )
        except psycopg2.OperationalError:
            conn = connect()
            continue
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
