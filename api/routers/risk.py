"""HazardGraph — Risk assessment API (stub).

Will be implemented in a future epic.
"""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["risk"])


@router.get("/api/v1/risk/scores")
async def get_risk_scores():
    """Return all risk scores (stub)."""
    return {"message": "not yet implemented"}


@router.get("/api/v1/risk/scores/{region_id}")
async def get_region_risk_score(region_id: str):
    """Return risk score for a specific region (stub)."""
    return {"message": "not yet implemented", "region_id": region_id}