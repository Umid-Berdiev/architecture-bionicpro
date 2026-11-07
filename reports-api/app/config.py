"""Runtime configuration, read from the environment (see docker-compose.yaml)."""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # Issuer as it appears in tokens (the browser talks to Keycloak on localhost:8080),
    # JWKS fetched over the internal docker network.
    keycloak_issuer: str = os.environ.get("KEYCLOAK_ISSUER", "http://localhost:8080/realms/reports-realm")
    keycloak_jwks_url: str = os.environ.get(
        "KEYCLOAK_JWKS_URL", "http://keycloak:8080/realms/reports-realm/protocol/openid-connect/certs")
    keycloak_audience: str = os.environ.get("KEYCLOAK_AUDIENCE", "reports-api")
    required_role: str = os.environ.get("REPORTS_REQUIRED_ROLE", "prothetic_user")

    clickhouse_host: str = os.environ.get("CLICKHOUSE_HOST", "clickhouse")
    clickhouse_port: int = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
    clickhouse_user: str = os.environ.get("CLICKHOUSE_USER", "reports")
    clickhouse_password: str = os.environ.get("CLICKHOUSE_PASSWORD", "")
    clickhouse_db: str = os.environ.get("CLICKHOUSE_DB", "reports")

    cors_origins: list = field(default_factory=lambda: os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","))
    default_period_days: int = int(os.environ.get("REPORTS_DEFAULT_PERIOD_DAYS", "7"))
