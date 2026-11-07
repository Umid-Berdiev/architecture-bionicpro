"""Read-only access to the ClickHouse mart. No aggregation happens here: the mart is pre-built by Airflow."""
from datetime import date, datetime
from typing import Protocol

import clickhouse_connect

from .config import Settings

MART_COLUMNS = [
    "report_date", "prosthesis_serial", "model", "side", "actions_count", "readings_count",
    "avg_reaction_ms", "p95_reaction_ms", "max_reaction_ms", "slow_actions_count", "avg_noise_level",
    "avg_battery_pct", "min_battery_pct", "error_count", "active_hours", "gestures",
]


class ReportsRepository(Protocol):
    def processed_until(self) -> datetime | None: ...
    def customer(self, user_id: str) -> dict | None: ...
    def daily_rows(self, user_id: str, date_from: date, date_to: date) -> list[dict]: ...


class ClickHouseReportsRepository:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = None

    @property
    def client(self):
        # Connect lazily so the API can start before ClickHouse is up.
        if self._client is None:
            s = self._settings
            self._client = clickhouse_connect.get_client(
                host=s.clickhouse_host, port=s.clickhouse_port, username=s.clickhouse_user,
                password=s.clickhouse_password, database=s.clickhouse_db)
        return self._client

    def processed_until(self) -> datetime | None:
        rows = self.client.query(
            "SELECT processed_until FROM etl_watermark FINAL WHERE pipeline = {p:String}",
            parameters={"p": "reports_mart"},
        ).result_rows
        return rows[0][0] if rows else None

    def customer(self, user_id: str) -> dict | None:
        rows = self.client.query(
            "SELECT username, full_name FROM crm_customers FINAL WHERE idp_user_id = {uid:UUID} LIMIT 1",
            parameters={"uid": user_id},
        ).result_rows
        return {"username": rows[0][0], "full_name": rows[0][1]} if rows else None

    def daily_rows(self, user_id: str, date_from: date, date_to: date) -> list[dict]:
        # Range read on the primary key (idp_user_id, report_date): only this user's rows are touched.
        result = self.client.query(
            f"""
            SELECT {", ".join(MART_COLUMNS)}
            FROM reports_mart FINAL
            WHERE idp_user_id = {{uid:UUID}} AND report_date BETWEEN {{d1:Date}} AND {{d2:Date}}
            ORDER BY report_date, prosthesis_serial
            """,
            parameters={"uid": user_id, "d1": date_from, "d2": date_to},
        )
        return [dict(zip(MART_COLUMNS, row)) for row in result.result_rows]
