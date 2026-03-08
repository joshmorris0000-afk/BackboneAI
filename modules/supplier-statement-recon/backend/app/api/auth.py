from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_ip,
    verify_password,
)
from app.models.shared import User
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/token", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user and user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=429, detail="Account temporarily locked — too many failed attempts")

    if not user or not verify_password(body.password, user.hashed_password) or not user.is_active:
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            await db.flush()

        await audit.log(
            db, action="login_failed", entity_type="user",
            client_id=user.client_id if user else None,
            actor_type="user", actor_ip=request.client.host,
            notes=f"Failed login attempt for {body.email}",
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)

    token_data = {"sub": str(user.id), "client_id": str(user.client_id), "role": user.role}
    access = create_access_token(token_data)
    refresh = create_refresh_token(token_data)

    claims = decode_token(refresh)
    user.refresh_token_jti = claims.get("jti")
    await db.flush()

    await audit.log(
        db, action="login_success", entity_type="user",
        entity_id=user.id, client_id=user.client_id,
        actor_type="user", actor_id=user.id, actor_ip=request.client.host,
    )

    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    claims = decode_token(body.refresh_token)
    if not claims or claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await db.get(User, claims["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    if user.refresh_token_jti != claims.get("jti"):
        raise HTTPException(status_code=401, detail="Refresh token already used")

    token_data = {"sub": str(user.id), "client_id": str(user.client_id), "role": user.role}
    access = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)

    new_claims = decode_token(new_refresh)
    user.refresh_token_jti = new_claims.get("jti")
    await db.flush()

    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
async def logout(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    claims = decode_token(body.refresh_token)
    if claims:
        user = await db.get(User, claims.get("sub"))
        if user:
            user.refresh_token_jti = None
            await db.flush()
