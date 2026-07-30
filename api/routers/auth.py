"""HazardGraph — Authentication API routes.

POST /api/v1/auth/login    — authenticate user, return JWT tokens
POST /api/v1/auth/refresh  — refresh access token
POST /api/v1/auth/logout   — blacklist current token
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import DbSession, RedisDep, get_db, get_redis
from auth.jwt_service import (
    create_access_token,
    create_refresh_token,
    verify_token,
    decode_payload,
)
from auth.password_service import verify_password, hash_password
from auth.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


# ── Schemas ────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    role: str
    user_id: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str


class LogoutRequest(BaseModel):
    token: str


# ── Routes ─────────────────────────────────────────────────


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: DbSession,
    redis: RedisDep,
):
    """Authenticate user and return JWT tokens.

    Rate limited: 5 attempts per 15 minutes per IP.
    """
    # Rate limit
    client_ip = request.client.host if request.client else "unknown"
    await rate_limiter.check_ip(
        ip=client_ip,
        endpoint="login",
        max_requests=5,
        window_seconds=900,
        redis_client=redis,
    )

    # Fetch user
    try:
        result = await db.execute(
            text("SELECT id, username, hashed_password, role FROM users WHERE username = :uname"),
            {"uname": body.username},
        )
        user = result.fetchone()
    except Exception as exc:
        logger.error("Database error during login: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed")

    if not user:
        logger.warning("Login attempt for unknown user: %s", body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    user_id, username, hashed_password, role = user

    if not verify_password(body.password, hashed_password):
        logger.warning("Invalid password for user: %s", body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Convert UUID to string for JWT and response
    user_id_str = str(user_id)

    # Generate tokens
    access_token = create_access_token(user_id_str, role)
    refresh_token = create_refresh_token(user_id_str)

    # Log to audit
    try:
        from models.postgres.audit import AuditLog
        log = AuditLog(
            action="login",
            entity_type="user",
            entity_id=user_id_str,
            details=f"User {username} logged in from {client_ip}",
        )
        db.add(log)
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to log audit: %s", exc)

    logger.info("User %s logged in successfully (role=%s)", username, role)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=role,
        user_id=user_id_str,
    )


@router.post("/auth/refresh", response_model=RefreshResponse)
async def refresh_token(
    body: RefreshRequest,
    db: DbSession,
    redis: RedisDep,
):
    """Refresh an expired access token using a valid refresh token."""
    try:
        payload = verify_token(body.refresh_token)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected refresh token",
        )

    # Check blacklist
    try:
        is_blacklisted = await redis.get(f"blacklist:{body.refresh_token}")
        if is_blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Redis down — allow refresh

    user_id_str = payload["sub"]

    # Fetch user role
    try:
        result = await db.execute(
            text("SELECT role FROM users WHERE id = :uid"),
            {"uid": user_id_str},
        )
        user = result.fetchone()
        role = user[0] if user else "viewer"
    except Exception:
        role = "viewer"

    new_access = create_access_token(user_id_str, role)
    return RefreshResponse(access_token=new_access)


@router.post("/auth/logout")
async def logout(
    body: LogoutRequest,
    redis: RedisDep,
):
    """Blacklist the current access token."""
    try:
        payload = decode_payload(body.token)
        exp = payload.get("exp", 0)
        now = datetime.now(timezone.utc).timestamp()
        ttl = max(int(exp - now), 3600)  # Default 1h if can't parse

        await redis.set(f"blacklist:{body.token}", "1", ex=ttl)
        logger.info("Token blacklisted (expires in %ds)", ttl)
    except Exception as exc:
        logger.warning("Logout blacklist failed: %s", exc)

    return {"detail": "Logged out successfully"}