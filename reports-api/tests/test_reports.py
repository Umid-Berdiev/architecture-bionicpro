"""Tests of the access rules and the period rule of GET /reports.

Token verification and ClickHouse are replaced with fakes: these tests cover the API's own logic,
not Keycloak or ClickHouse.
"""
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import Principal
from app.config import Settings
from app.main import create_app
from app.service import NotProcessedYet, resolve_period

ME = "00000000-0000-4000-8000-000000000301"
OTHER = "00000000-0000-4000-8000-000000000302"
PROCESSED_UNTIL = datetime(2026, 11, 8, 9, 0, 0)

TOKENS = {
    "token-prothetic1": Principal(ME, "prothetic1", frozenset({"prothetic_user"})),
    "token-prothetic2": Principal(OTHER, "prothetic2", frozenset({"prothetic_user"})),
    "token-user1": Principal("00000000-0000-4000-8000-000000000101", "user1", frozenset({"user"})),
}


class FakeVerifier:
    def verify(self, token: str) -> Principal:
        if token not in TOKENS:
            raise HTTPException(401, "invalid token: InvalidSignatureError")
        return TOKENS[token]


def mart_row(day: date, serial: str = "BP-ARM-2024-0001", actions: int = 100) -> dict:
    return {
        "report_date": day, "prosthesis_serial": serial, "model": "BionicArm Pro 2", "side": "right",
        "actions_count": actions, "readings_count": actions + 20, "avg_reaction_ms": 80.0,
        "p95_reaction_ms": 120, "max_reaction_ms": 180, "slow_actions_count": 10,
        "avg_noise_level": 0.2, "avg_battery_pct": 60.0, "min_battery_pct": 15, "error_count": 1,
        "active_hours": 12, "gestures": {"grip": 50, "rest": 20},
    }


class FakeRepository:
    def __init__(self, processed_until=PROCESSED_UNTIL):
        self._processed_until = processed_until
        self.rows = {ME: [mart_row(PROCESSED_UNTIL.date() - timedelta(days=d)) for d in range(10)],
                     OTHER: [mart_row(PROCESSED_UNTIL.date(), "BP-ARM-2024-0002")]}
        self.customers = {ME: {"username": "prothetic1", "full_name": "Ivanov"},
                          OTHER: {"username": "prothetic2", "full_name": "Smirnova"}}
        self.queried_user_ids = []

    def processed_until(self):
        return self._processed_until

    def customer(self, user_id):
        return self.customers.get(user_id)

    def daily_rows(self, user_id, date_from, date_to):
        self.queried_user_ids.append(user_id)
        # Same ordering as the ClickHouse query: by date, then prosthesis.
        rows = [r for r in self.rows.get(user_id, []) if date_from <= r["report_date"] <= date_to]
        return sorted(rows, key=lambda r: (r["report_date"], r["prosthesis_serial"]))


@pytest.fixture
def repo():
    return FakeRepository()


@pytest.fixture
def client(repo):
    app = create_app(Settings())
    app.state.verifier = FakeVerifier()
    app.state.repository = repo
    return TestClient(app)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- authentication
def test_unauthenticated_request_is_rejected(client):
    assert client.get("/reports").status_code == 401


def test_invalid_token_is_rejected(client):
    assert client.get("/reports", headers=auth("garbage")).status_code == 401


def test_user_without_prothetic_role_is_forbidden(client):
    assert client.get("/reports", headers=auth("token-user1")).status_code == 403


# ---------------------------------------------------------------- authorization: own report only
def test_own_report_is_returned_from_the_mart(client, repo):
    r = client.get("/reports", headers=auth("token-prothetic1"))
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["id"] == ME
    assert len(body["days"]) == 7                       # default period: 7 processed days
    assert body["period"]["to"] == PROCESSED_UNTIL.date().isoformat()
    assert body["days"][-1]["partial"] is True          # watermark day is not complete yet
    assert body["summary"]["actions_count"] == 700
    assert repo.queried_user_ids == [ME]                # the query is always for the token's user


def test_explicit_own_user_id_is_allowed(client):
    assert client.get(f"/reports?user_id={ME}", headers=auth("token-prothetic1")).status_code == 200


def test_other_users_report_is_forbidden(client, repo):
    r = client.get(f"/reports?user_id={OTHER}", headers=auth("token-prothetic1"))
    assert r.status_code == 403
    assert repo.queried_user_ids == []                  # the mart is not even queried


def test_each_user_sees_only_their_own_rows(client):
    r = client.get("/reports", headers=auth("token-prothetic2"))
    assert r.status_code == 200
    assert {d["prosthesis_serial"] for d in r.json()["days"]} == {"BP-ARM-2024-0002"}


# ---------------------------------------------------------------- period: only processed data
def test_period_beyond_watermark_is_clamped(client):
    future = (PROCESSED_UNTIL.date() + timedelta(days=3)).isoformat()
    start = (PROCESSED_UNTIL.date() - timedelta(days=2)).isoformat()
    r = client.get(f"/reports?from={start}&to={future}", headers=auth("token-prothetic1"))
    assert r.status_code == 200
    period = r.json()["period"]
    assert period["clamped"] is True
    assert period["to"] == PROCESSED_UNTIL.date().isoformat()
    assert period["requested_to"] == future


def test_period_entirely_beyond_watermark_is_rejected(client):
    start = (PROCESSED_UNTIL.date() + timedelta(days=1)).isoformat()
    r = client.get(f"/reports?from={start}", headers=auth("token-prothetic1"))
    assert r.status_code == 422
    assert "data_processed_until" in r.json()


def test_mart_not_built_yet(repo):
    app = create_app(Settings())
    app.state.verifier = FakeVerifier()
    app.state.repository = FakeRepository(processed_until=None)
    assert TestClient(app).get("/reports", headers=auth("token-prothetic1")).status_code == 503


def test_csv_download(client):
    r = client.get("/reports?format=csv", headers=auth("token-prothetic1"))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in r.headers["content-disposition"]
    assert r.text.splitlines()[0].startswith("report_date,prosthesis_serial")


def test_resolve_period_rules():
    p = resolve_period(None, None, PROCESSED_UNTIL, default_days=7)
    assert (p.date_from, p.date_to, p.clamped) == (date(2026, 11, 2), date(2026, 11, 8), False)
    with pytest.raises(NotProcessedYet):
        resolve_period(date(2026, 11, 9), date(2026, 11, 10), PROCESSED_UNTIL, 7)
