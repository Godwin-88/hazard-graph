"""HazardGraph — GET /api/v1/health endpoint.

Returns system health status including Neo4j, PostgreSQL, Redis,
and scheduler job info. Cached in Redis for 30 seconds.
"""

import json
import logging

from fastapi import APIRouter
from sqlalchemy import text, select, desc

from config.settings import settings
from db.neo4j_client import neo4j_client
from db.postgres_client import engine, async_session_factory
from db.redis_client import redis_client
from models.postgres.jobs import JobRun
from scheduler.jobs import scheduler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
async def health_check():
    """Return comprehensive system health status.

    Results are cached in Redis for 30 seconds.
    """
    # Try Redis cache first
    cached = await redis_client.get("health:status")
    if cached:
        try:
            return json.loads(cached)
        except (json.JSONDecodeError, TypeError):
            pass

    # Gather health data
    neo4j_status = await neo4j_client.health_check()

    # PostgreSQL connectivity check
    postgres_connected = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            postgres_connected = True
    except Exception as exc:
        logger.warning("PostgreSQL health check failed: %s", exc)

    redis_status = await redis_client.health_check()

    # Gather scheduler job info
    jobs_info = []
    for job in scheduler.get_jobs():
        last_run = None
        status = "scheduled"
        # Try to get last run from PostgreSQL
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(JobRun)
                    .where(JobRun.job_name == job.id)
                    .order_by(desc(JobRun.started_at))
                    .limit(1)
                )
                last_run_record = result.scalar_one_or_none()
                if last_run_record:
                    last_run = last_run_record.started_at.isoformat() if last_run_record.started_at else None
                    status = last_run_record.status
        except Exception:
            pass

        jobs_info.append({
            "name": job.id or job.name,
            "last_run": last_run,
            "status": status,
        })

    # Determine overall status
    all_connected = neo4j_status["connected"] and postgres_connected and redis_status["connected"]
    overall_status = "ok" if all_connected else "degraded"
    if not neo4j_status["connected"] and not postgres_connected and not redis_status["connected"]:
        overall_status = "down"

    response = {
        "status": overall_status,
        "neo4j": neo4j_status,
        "postgres": {"connected": postgres_connected},
        "redis": redis_status,
        "jobs": jobs_info,
        "version": settings.app_version,
    }

    # Cache for 30 seconds
    try:
        await redis_client.set("health:status", json.dumps(response), ttl=30)
    except Exception as exc:
        logger.warning("Failed to cache health status: %s", exc)

    return response