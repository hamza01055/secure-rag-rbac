"""Password hashing and JWT encode/decode. No authorization logic lives here."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.errors import unauthorized

_pwd = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _pwd.verify(raw, hashed)


def create_access_token(subject: str, *, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl_seconds),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "typ": "access",
        **(extra or {}),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(seconds=settings.refresh_token_ttl_seconds),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "typ": "refresh",
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str, *, expect: str = "access") -> dict[str, Any]:
    """Validate signature, expiry, issuer, audience, and token type.

    The algorithm is pinned. Accepting the algorithm from the header is how
    'alg: none' forgery works.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except JWTError:
        raise unauthorized("invalid token")

    if claims.get("typ") != expect:
        raise unauthorized("wrong token type")
    return claims
