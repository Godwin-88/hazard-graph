"""HazardGraph — GET /api/v1/lineage endpoint.

Returns all DataSource nodes from Neo4j.
Cached in Redis for 5 minutes.
"""

import json
import logging

from fastapi import APIRouter

from db.redis_client import redis_client
from graph.lineage import get_lineage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["lineage"])


@router.get("/lineage")
async def lineage():
    """Return all DataSource nodes from the knowledge graph.

    Results are cached in Redis for 5 minutes (300 seconds).
    """
    cached = await redis_client.get("lineage:all")
    if cached:
        try:
            return json.loads(cached)
        except (json.JSONDecodeError, TypeError):
            pass

    sources = await get_lineage()

    # Cache for 5 minutes
    try:
        await redis_client.set("lineage:all", json.dumps(sources, default=str), ttl=300)
    except Exception as exc:
        logger.warning("Failed to cache lineage response: %s", exc)

    return sources