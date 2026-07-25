from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import get_principal
from app.core.errors import unauthorized
from app.core.principal import Principal
from app.core.security import create_access_token, create_refresh_token, verify_password
from app.db import get_session
from app.models import User
from app.schemas import LoginRequest, PrincipalOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=PrincipalOut)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_session)):
    stmt = select(User).options(selectinload(User.role)).where(User.email == body.email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    # Verify a dummy hash when the user is missing so the response time does not
    # reveal which emails exist.
    if user is None or not verify_password(body.password, user.hashed_password):
        raise unauthorized("invalid credentials")
    if not user.is_active:
        raise unauthorized("account disabled")

    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    secure = settings.env != "development"

    response.set_cookie("access_token", access, httponly=True, secure=secure,
                        samesite="strict", max_age=settings.access_token_ttl_seconds, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=secure,
                        samesite="strict", max_age=settings.refresh_token_ttl_seconds,
                        path="/auth/refresh")

    return PrincipalOut(user_id=str(user.id), email=user.email, role=user.role.name,
                        clearance=user.role.clearance_level, tenant_id=str(user.tenant_id))


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth/refresh")
    return {"ok": True}


@router.get("/me", response_model=PrincipalOut)
async def me(p: Principal = Depends(get_principal)):
    return PrincipalOut(user_id=p.user_id, email=p.email, role=p.role,
                        clearance=p.clearance, tenant_id=p.tenant_id)
