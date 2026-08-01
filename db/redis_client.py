"""HazardGraph — aioredis singleton with cache decorator factory."""

import functools
import hashlib
import json
import logging
from typing import Any, Callable, Optional

import redis.asyncio as aioredis

from config.settings import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client wrapper with connection pool."""

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """Initialise the Redis connection pool."""
        if self._redis is not None:
            return
        self._redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
        await self._redis.ping()
        logger.info("Redis connected to %s", settings.redis_url)

    async def close(self) -> None:
        """Close the Redis connection pool."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
            logger.info("Redis connection closed")

    @property
    def raw(self):
        """Access the underlying raw Redis connection for advanced operations.

        Use this for sorted sets, pipelines, and other Redis features
        not exposed by the RedisClient wrapper.
        """
        return self._redis

    async def get(self, key: str) -> Optional[str]:
        """Get a value by key."""
        if self._redis is None:
            return None
        try:
            return await self._redis.get(key)
        except Exception as exc:
            logger.warning("Redis GET failed for key=%s: %s", key, exc)
            return None

    async def set(self, key: str, value: str, ttl: int = 300) -> bool:
        """Set a value with TTL in seconds."""
        if self._redis is None:
            return False
        try:
            return await self._redis.setex(key, ttl, value)
        except Exception as exc:
            logger.warning("Redis SET failed for key=%s: %s", key, exc)
            return False

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys. Returns number of keys removed."""
        if self._redis is None:
            return 0
        try:
            return await self._redis.delete(*keys)
        except Exception as exc:
            logger.warning("Redis DELETE failed for keys=%s: %s", keys, exc)
            return 0

    async def health_check(self) -> dict:
        """Check Redis connectivity and return hit rate info."""
        connected = False
        hit_rate = 0.0
        try:
            if self._redis is None:
                await self.connect()
            await self._redis.ping()
            connected = True
            # Attempt to get cache stats
            info = await self._redis.info("stats")
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 1)
            total = hits + misses
            hit_rate = round(hits / total, 4) if total > 0 else 0.0
        except Exception as exc:
            logger.warning("Redis health check failed: %s", exc)
        return {"connected": connected, "hit_rate": hit_rate}

    def cache(self, ttl: int = 300) -> Callable:
        """Decorator factory: caches async function return value in Redis.

        The cache key is derived from the function name and JSON-serialised
        positional/keyword arguments.
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                # Build a deterministic cache key
                key_parts = [func.__name__]
                key_parts.append(json.dumps(args, sort_keys=True, default=str))
                key_parts.append(json.dumps(kwargs, sort_keys=True, default=str))
                raw_key = ":".join(key_parts)
                cache_key = f"cache:{hashlib.sha256(raw_key.encode()).hexdigest()}"

                # Try cache hit
                cached = await self.get(cache_key)
                if cached is not None:
                    try:
                        return json.loads(cached)
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Execute the original function
                result = await func(*args, **kwargs)

                # Store in cache
                try:
                    await self.set(cache_key, json.dumps(result, default=str), ttl)
                except Exception as exc:
                    logger.warning("Failed to cache result for %s: %s", func.__name__, exc)

                return result
            return wrapper
        return decorator


# Singleton
redis_client = RedisClient()


# ── FastAPI dependency ────────────────────────────────────


async def get_redis():
    """FastAPI dependency yielding the Redis client singleton."""
    return redis_client