"""Report assembly: period rules against the ETL watermark and summary over pre-aggregated rows."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from .auth import Principal
from .repository import ReportsRepository


class ReportError(Exception):
    status_code = 400

    def __init__(self, detail: str, **extra):
        super().__init__(detail)
        self.detail = detail
        self.extra = extra


class InvalidPeriod(ReportError):
    status_code = 422


class NotProcessedYet(ReportError):
    """The whole requested range lies beyond what Airflow has processed."""
    status_code = 422


class NoDataForUser(ReportError):
    status_code = 404


class MartNotReady(ReportError):
    status_code = 503


@dataclass(frozen=True)
class Period:
    date_from: date
    date_to: date          # effective end, never beyond the processed period
    requested_to: date
    clamped: bool


def resolve_period(date_from: date | None, date_to: date | None, processed_until: datetime,
                   default_days: int) -> Period:
    """Apply the "only already processed data" rule.

    * no dates: the last ``default_days`` processed days;
    * end beyond the watermark: clamp to the watermark and flag it;
    * start beyond the watermark: nothing to report yet -> error.
    """
    available_to = processed_until.date()
    if date_from is not None and date_to is not None and date_from > date_to:
        raise InvalidPeriod("'from' must not be after 'to'")
    requested_to = date_to if date_to is not None else available_to
    if date_from is None:
        date_from = min(requested_to, available_to) - timedelta(days=default_days - 1)
    if date_from > available_to:
        raise NotProcessedYet(
            f"data is processed only until {processed_until.isoformat()}Z; requested period starts later",
            data_processed_until=processed_until.isoformat() + "Z",
        )
    clamped = requested_to > available_to
    return Period(date_from=date_from, date_to=min(requested_to, available_to),
                  requested_to=requested_to, clamped=clamped)


def build_report(principal: Principal, repo: ReportsRepository, date_from: date | None,
                 date_to: date | None, default_days: int) -> dict:
    processed_until = repo.processed_until()
    if processed_until is None:
        raise MartNotReady("the report mart has not been built yet; wait for the first ETL run")

    period = resolve_period(date_from, date_to, processed_until, default_days)

    customer = repo.customer(principal.sub)
    if customer is None:
        raise NoDataForUser("no prosthesis is registered for this account in the CRM")

    rows = repo.daily_rows(principal.sub, period.date_from, period.date_to)
    # The watermark day is complete only if the ETL ran at the very end of it.
    partial_day = processed_until.date() if processed_until.time() < time(23, 59) else None
    days = [{**row, "partial": row["report_date"] == partial_day} for row in rows]

    return {
        "user": {"id": principal.sub, "username": customer["username"], "full_name": customer["full_name"]},
        "period": {
            "from": period.date_from, "to": period.date_to,
            "requested_to": period.requested_to, "clamped": period.clamped,
        },
        "data_processed_until": processed_until.replace(tzinfo=timezone.utc),
        "generated_at": datetime.now(timezone.utc),
        "summary": summarize(rows),
        "days": days,
    }


def summarize(rows: list[dict]) -> dict:
    actions = sum(r["actions_count"] for r in rows)
    weighted_reaction = sum(r["avg_reaction_ms"] * r["actions_count"] for r in rows)
    readings = sum(r["readings_count"] for r in rows)
    weighted_noise = sum(r["avg_noise_level"] * r["readings_count"] for r in rows)
    slow = sum(r["slow_actions_count"] for r in rows)
    return {
        "days": len({r["report_date"] for r in rows}),
        "prostheses": sorted({r["prosthesis_serial"] for r in rows}),
        "actions_count": actions,
        "avg_reaction_ms": round(weighted_reaction / actions, 1) if actions else None,
        "max_reaction_ms": max((r["max_reaction_ms"] for r in rows), default=None),
        "slow_actions_share": round(slow / actions, 4) if actions else None,
        "avg_noise_level": round(weighted_noise / readings, 3) if readings else None,
        "min_battery_pct": min((r["min_battery_pct"] for r in rows), default=None),
        "error_count": sum(r["error_count"] for r in rows),
    }
