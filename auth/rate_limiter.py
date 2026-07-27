"""HazardGraph — Redis sliding window rate limiter.

Uses Redis sorted sets to implement sliding window rate limiting.
Raises HTTPException 429 if limit exceeded.
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding window rate limiter backed by Redis sorted sets."""

    async def check(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        redis_client,
    ) -> None:
        """Check if request is within rate limit.

        Args:
            key: Rate limit key (e.g., "rl:192.168.1.1:login")
            max_requests: Maximum allowed requests in window
            window_seconds: Sliding window duration in seconds
            redis_client: Redis client with execute method

        Raises:
            HTTPException 429 if rate limit exceeded
        """
        if not redis_client:
            logger.warning("Redis client not available — rate limiting disabled")
            return

        try:
            redis_key = f"rl:{key}"
            now = datetime.now(timezone.utc).timestamp()
            window_start = now - window_seconds

            from redis import asyncio as aioredis
            # Use the underlying Redis connection
            conn = redis_client

            # Remove old entries outside window
            await conn.zremrangebyscore(redis_key, 0, window_start)
            # Add current request
            await conn.zadd(redis_key, {str(now): now})
            # Count requests in window
            count = await conn.zcard(redis_key)
            # Set TTL
            await conn.expire(redis_key, window_seconds)

            if count > max_requests:
                logger.warning("Rate limit exceeded for %s: %d/%d", key, count, max_requests)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds}s.",
                )

            logger.debug("Rate limit OK for %s: %d/%d", key, count, max_requests)

        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Rate limiter error for %s: %s", key, exc)
            # Allow request if Redis is down — fail open for production safety
            return

    async def check_ip(
        self,
        ip: str,
        endpoint: str,
        max_requests: int,
        window_seconds: int,
        redis_client,
    ) -> None:
        """Convenience wrapper for IP-based rate limiting."""
        key = f"{ip}:{endpoint}"
        await self.check(key, max_requests, window_seconds, redis_client)


rate_limiter = RateLimiter()