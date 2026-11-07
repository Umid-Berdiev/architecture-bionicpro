"""Hourly ETL that feeds the BionicPRO reports mart in ClickHouse.

Sources
    crm_db        PostgreSQL, emulated CRM: customers and their prostheses (small, reloaded fully).
    telemetry_db  PostgreSQL, operational telemetry written by the API from the prosthesis chips
                  (large, loaded incrementally by recorded_at).

Targets (ClickHouse, database ``reports``)
    crm_customers, crm_prostheses   raw copies of the CRM dimensions (ReplacingMergeTree by loaded_at)
    telemetry_raw                   raw telemetry facts
    reports_mart                    one row per user / prosthesis / day, ordered by (idp_user_id, report_date)
    etl_watermark                   "processed_until" that the reports API never reports beyond

Every run processes data up to its ``data_interval_end``; only the days touched by newly loaded
telemetry are rebuilt in the mart, then the watermark is advanced to ``data_interval_end``.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import clickhouse_connect
import pendulum
from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook

log = logging.getLogger(__name__)

PIPELINE = "reports_mart"
TARGET_REACTION_MS = 100  # product requirement: reaction time should not exceed 100 ms
CHUNK = 20_000

CUSTOMER_COLUMNS = ["customer_id", "idp_user_id", "username", "full_name", "email", "country", "loaded_at"]
PROSTHESIS_COLUMNS = ["prosthesis_id", "customer_id", "serial_number", "model", "side",
                      "firmware_version", "delivered_at", "loaded_at"]
TELEMETRY_COLUMNS = ["telemetry_id", "prosthesis_serial", "recorded_at", "gesture", "reaction_ms",
                     "myo_noise_level", "battery_pct", "error_code"]


def clickhouse():
    return clickhouse_connect.get_client(
        host=os.environ.get("CLICKHOUSE_HOST", "clickhouse"),
        port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
        username=os.environ.get("CLICKHOUSE_USER", "reports"),
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
        database=os.environ.get("CLICKHOUSE_DB", "reports"),
    )


def _naive_utc(dt: datetime) -> datetime:
    """ClickHouse DateTime has no zone: store everything as naive UTC."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


@dag(
    dag_id="bionicpro_reports_etl",
    description="CRM + telemetry -> ClickHouse reports mart (hourly)",
    schedule="@hourly",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "bionicpro", "retries": 2, "retry_delay": timedelta(minutes=2)},
    tags=["bionicpro", "reports", "clickhouse"],
    doc_md=__doc__,
)
def bionicpro_reports_etl():

    @task
    def extract_crm() -> dict:
        """Full reload of the CRM dimensions (a few thousand rows at most)."""
        pg = PostgresHook(postgres_conn_id="crm_db")
        loaded_at = _naive_utc(datetime.now(timezone.utc))
        customers = pg.get_records(
            "SELECT id, idp_user_id, username, full_name, email, country FROM customers ORDER BY id")
        prostheses = pg.get_records(
            "SELECT id, customer_id, serial_number, model, side, firmware_version, delivered_at "
            "FROM prostheses ORDER BY id")
        ch = clickhouse()
        ch.insert("crm_customers", [[*row, loaded_at] for row in customers], column_names=CUSTOMER_COLUMNS)
        ch.insert("crm_prostheses", [[*row, loaded_at] for row in prostheses], column_names=PROSTHESIS_COLUMNS)
        log.info("crm: %d customers, %d prostheses", len(customers), len(prostheses))
        return {"customers": len(customers), "prostheses": len(prostheses)}

    @task
    def extract_telemetry(data_interval_end: pendulum.DateTime | None = None) -> dict:
        """Incremental load: rows newer than what ClickHouse already has, up to data_interval_end."""
        upper = data_interval_end.in_timezone("UTC")
        ch = clickhouse()
        last = ch.query("SELECT max(recorded_at) FROM telemetry_raw").result_rows[0][0]
        lower = last.replace(tzinfo=timezone.utc) if last else datetime(1970, 1, 1, tzinfo=timezone.utc)

        pg = PostgresHook(postgres_conn_id="telemetry_db")
        rows = pg.get_records(
            "SELECT id, prosthesis_serial, (recorded_at AT TIME ZONE 'UTC'), gesture, reaction_ms, "
            "myo_noise_level, battery_pct, coalesce(error_code, '') "
            "FROM telemetry WHERE recorded_at > %s AND recorded_at <= %s ORDER BY id",
            parameters=(lower, upper),
        )
        for start in range(0, len(rows), CHUNK):
            chunk = [[r[0], r[1], r[2], r[3], r[4], float(r[5]), r[6], r[7]] for r in rows[start:start + CHUNK]]
            ch.insert("telemetry_raw", chunk, column_names=TELEMETRY_COLUMNS)

        first_day = min(r[2] for r in rows).date().isoformat() if rows else None
        log.info("telemetry: %d rows in (%s, %s], first day %s", len(rows), lower, upper, first_day)
        return {"rows": len(rows), "from_date": first_day, "to_date": upper.date().isoformat()}

    @task
    def build_mart(telemetry: dict) -> dict:
        """Rebuild reports_mart for the days that received new telemetry in this run."""
        if not telemetry["rows"]:
            log.info("no new telemetry, mart unchanged")
            return {"days_rebuilt": 0}
        ch = clickhouse()
        ch.command(
            f"""
            INSERT INTO reports_mart
            SELECT
                c.idp_user_id,
                toDate(t.recorded_at)                                  AS report_date,
                t.prosthesis_serial,
                c.username,
                c.full_name,
                p.model,
                p.side,
                countIf(t.gesture != 'rest')                           AS actions_count,
                count()                                                AS readings_count,
                avgIf(t.reaction_ms, t.gesture != 'rest')              AS avg_reaction_ms,
                toUInt16(quantileIf(0.95)(t.reaction_ms, t.gesture != 'rest')) AS p95_reaction_ms,
                maxIf(t.reaction_ms, t.gesture != 'rest')              AS max_reaction_ms,
                countIf(t.gesture != 'rest' AND t.reaction_ms > {TARGET_REACTION_MS}) AS slow_actions_count,
                avg(t.myo_noise_level)                                 AS avg_noise_level,
                avg(t.battery_pct)                                     AS avg_battery_pct,
                min(t.battery_pct)                                     AS min_battery_pct,
                countIf(t.error_code != '')                            AS error_count,
                toUInt8(uniqExact(toHour(t.recorded_at)))              AS active_hours,
                CAST(sumMap(map(t.gesture, toUInt32(1))), 'Map(String, UInt32)') AS gestures,
                now()                                                  AS built_at
            FROM telemetry_raw AS t
            INNER JOIN (SELECT * FROM crm_prostheses FINAL) AS p ON p.serial_number = t.prosthesis_serial
            INNER JOIN (SELECT * FROM crm_customers FINAL)  AS c ON c.customer_id = p.customer_id
            WHERE toDate(t.recorded_at) BETWEEN {{from_date:Date}} AND {{to_date:Date}}
            GROUP BY c.idp_user_id, report_date, t.prosthesis_serial, c.username, c.full_name, p.model, p.side
            """,
            parameters={"from_date": telemetry["from_date"], "to_date": telemetry["to_date"]},
        )
        days = (datetime.fromisoformat(telemetry["to_date"]) - datetime.fromisoformat(telemetry["from_date"])).days + 1
        log.info("mart rebuilt for %d day(s): %s .. %s", days, telemetry["from_date"], telemetry["to_date"])
        return {"days_rebuilt": days}

    @task
    def update_watermark(mart: dict, data_interval_end: pendulum.DateTime | None = None, run_id: str | None = None):
        """Publish the period that is now safe to report on."""
        processed_until = _naive_utc(data_interval_end)
        clickhouse().insert(
            "etl_watermark",
            [[PIPELINE, processed_until, run_id, _naive_utc(datetime.now(timezone.utc))]],
            column_names=["pipeline", "processed_until", "dag_run_id", "updated_at"],
        )
        log.info("watermark %s -> %s (%s)", PIPELINE, processed_until, run_id)

    crm = extract_crm()
    telemetry = extract_telemetry()
    crm >> telemetry
    update_watermark(build_mart(telemetry))


bionicpro_reports_etl()
