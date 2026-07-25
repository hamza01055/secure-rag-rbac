"""FastAPI dependencies. The only place a Principal is created."""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import forbidden, unauthorized
from app.core.principal import Principal
from app.core.security import decode_token
from app.db import get_session
from app.models import User


async def get_principal(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> Principal:
    """Resolve identity from the cookie, then re-read the role from the database.

    The database read costs one indexed lookup and buys immediate revocation:
    deactivate a user and their next request fails, rather than succeeding until
    the token expires. For very high-volume deployments, replace it with a
    role_version claim checked against a cached version map — but do not simply
    trust a long-lived claim.
    """
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else None
    if not token:
        raise unauthorized()

    claims = decode_token(token, expect="access")

    stmt = (
        select(User)
        .options(selectinload(User.role))
        .where(User.id == claims["sub"])
    )
    user = (await db.execute(stmt)).scalar_one_or_none()

    if user is None or not user.is_active:
        raise unauthorized("unknown or inactive principal")

    return Principal(
        user_id=str(user.id),
        email=user.email,
        role=user.role.name,
        clearance=user.role.clearance_level,
        tenant_id=str(user.tenant_id),
        is_admin=user.role.name == "Admin",
    )


async def require_admin(p: Principal = Depends(get_principal)) -> Principal:
    if not p.is_admin:
        raise forbidden("admin only")
    return p
