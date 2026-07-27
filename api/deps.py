"""HazardGraph — FastAPI dependency injectors.

Provides reusable dependencies for database session, Neo4j session,
and Redis client injection into route handlers.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.neo4j_client import neo4j_client
from db.postgres_client import get_db as _get_db_session
from db.redis_client import redis_client


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async PostgreSQL session."""
    async for session in _get_db_session():
        yield session


async def get_neo4j():
    """Dependency that returns the Neo4j client singleton."""
    return neo4j_client


async def get_redis():
    """Dependency that returns the Redis client singleton."""
    return redis_client


# Type annotations for FastAPI injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
Neo4jDep = Annotated[object, Depends(get_neo4j)]
RedisDep = Annotated[object, Depends(get_redis)]
