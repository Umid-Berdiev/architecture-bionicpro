"""BionicPRO reports API.

GET /reports returns the prosthesis usage report of the authenticated user, read from the
ClickHouse mart that Airflow builds. A user can only ever get their own report: the user id is
taken from the token, and an explicit ``user_id`` that differs from it is rejected with 403.
"""
import csv
import io
from datetime import date
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .auth import Principal, TokenVerifier, require_role
from .config import Settings
from .repository import ClickHouseReportsRepository, ReportsRepository
from .service import ReportError, build_report

CSV_COLUMNS = [
    "report_date", "prosthesis_serial", "model", "side", "actions_count", "avg_reaction_ms",
    "p95_reaction_ms", "max_reaction_ms", "slow_actions_count", "avg_noise_level", "avg_battery_pct",
    "min_battery_pct", "error_count", "active_hours", "partial",
]


def get_repository(request: Request) -> ReportsRepository:
    return request.app.state.repository


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="BionicPRO Reports API", version="1.0.0")
    app.state.settings = settings
    app.state.verifier = TokenVerifier(settings.keycloak_jwks_url, settings.keycloak_issuer, settings.keycloak_audience)
    app.state.repository = ClickHouseReportsRepository(settings)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type"], expose_headers=["Content-Disposition"],
    )

    @app.exception_handler(ReportError)
    async def report_error_handler(_: Request, exc: ReportError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, **exc.extra})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/reports")
    def get_report(
        user_id: UUID | None = Query(None, description="Optional; must be the caller's own id"),
        date_from: date | None = Query(None, alias="from"),
        date_to: date | None = Query(None, alias="to"),
        format: str = Query("json", pattern="^(json|csv)$"),
        principal: Principal = Depends(require_role(settings.required_role)),
        repo: ReportsRepository = Depends(get_repository),
    ):
        if user_id is not None and str(user_id) != principal.sub:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "a report is available only for your own account")

        report = build_report(principal, repo, date_from, date_to, settings.default_period_days)
        if format == "csv":
            return csv_response(report)
        return report

    return app


def csv_response(report: dict) -> Response:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in report["days"]:
        writer.writerow(row)
    filename = f"bionicpro-report-{report['user']['username']}-{report['period']['from']}-{report['period']['to']}.csv"
    return Response(
        content=buf.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app = create_app()
