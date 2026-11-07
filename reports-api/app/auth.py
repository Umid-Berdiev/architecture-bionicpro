"""Bearer-token authentication against Keycloak.

The API is a pure resource server: it never talks to Keycloak on behalf of the user. A token is
accepted only if its signature matches a key from the realm's JWKS, and its issuer, audience and
expiry are right. Roles come from the ``realm_access.roles`` claim.
"""
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientConnectionError

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    sub: str            # stable Keycloak user id; the CRM stores it as idp_user_id
    username: str
    roles: frozenset


class TokenVerifier:
    def __init__(self, jwks_url: str, issuer: str, audience: str):
        self._jwks = PyJWKClient(jwks_url, cache_keys=True, lifespan=300)
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> Principal:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except PyJWKClientConnectionError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "identity provider unavailable") from exc
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                f"invalid token: {type(exc).__name__}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        roles = frozenset(claims.get("realm_access", {}).get("roles", []))
        return Principal(sub=claims["sub"], username=claims.get("preferred_username", ""), roles=roles)


def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "authentication required", headers={"WWW-Authenticate": "Bearer"})
    verifier: TokenVerifier = request.app.state.verifier
    return verifier.verify(credentials.credentials)


def require_role(role: str):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if role not in principal.roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"role '{role}' required")
        return principal

    return dependency
