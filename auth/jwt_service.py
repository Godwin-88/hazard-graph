"""HazardGraph — JWT token creation, verification, and blacklisting.

Tokens stored in memory only on frontend side. Refresh token issued
for 7-day session persistence.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config.settings import settings
from api.deps import get_redis

logger = logging.getLogger(__name__)

SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_EXPIRE_DAYS = 7

security = HTTPBearer(auto_error=False)


def create_access_token(user_id: Any, role: str) -> str:
    """Create a JWT access token with user info.

    Args:
        user_id: PostgreSQL user ID (int or UUID)
        role: User role (admin, officer, viewer)

    Returns:
        Encoded JWT string
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: Any) -> str:
    """Create a JWT refresh token with longer expiry.

    Args:
        user_id: PostgreSQL user ID (int or UUID)

    Returns:
        Encoded JWT refresh token string
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict[str, Any]:
    """Verify a JWT token and return its payload.

    Args:
        token: JWT string

    Returns:
        Decoded payload dict

    Raises:
        HTTPException 401 if token is invalid, expired, or blacklisted
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_payload(token: str) -> dict[str, Any]:
    """Decode token payload without verification.

    Useful for extracting info from expired tokens (e.g., for refresh).

    Args:
        token: JWT string

    Returns:
        Decoded payload dict
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
    except jwt.InvalidTokenError:
        return {}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    redis=Depends(get_redis),
):
    """Extract and verify JWT from Authorization header.

    Dependencies:
        - HTTPBearer security scheme
        - Redis client for blacklist check

    Returns:
        Decoded JWT payload dict

    Raises:
        HTTPException 401 if not authenticated or token revoked
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    token = credentials.credentials

    # Check blacklist
    try:
        is_blacklisted = await redis.get(f"blacklist:{token}")
        if is_blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )
    except HTTPException:
        raise
    except Exception:
        pass

    payload = verify_token(token)
    return payload


async def require_officer(user=Depends(get_current_user)):
    """Require officer or admin role."""
    if user.get("role") not in ("officer", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Officer or admin role required",
        )
    return user


async def require_admin(user=Depends(get_current_user)):
    """Require admin role."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user