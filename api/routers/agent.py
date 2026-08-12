"""HazardGraph — DataHub-powered LangGraph agent API.

POST /api/v1/agent/query — query the HazardGraph intelligence agent
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth.jwt_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class AgentQueryRequest(BaseModel):
    query: str = Field(..., description="Question for the HazardGraph agent")
    region: str | None = Field(None, description="Optional region filter")
    alert_id: str | None = Field(None, description="Optional alert ID for lineage tracing")


@router.post("/query")
async def query_hazard_agent(
    body: AgentQueryRequest,
    _user=Depends(get_current_user),
):
    """Query the DataHub-powered HazardGraph LangGraph agent.

    Example queries:
    - "Why was the Mandera alert dispatched on Monday?"
    - "Which models are underperforming this week?"
    - "Is the CHIRPS data fresh enough to trust this week's forecasts?"
    - "What is the contagion risk from Somalia to Ethiopia if the BMA score exceeds 0.7?"
    """
    from agents.hazard_agent import build_hazard_agent

    try:
        agent = build_hazard_agent()
        result = await agent.ainvoke({
            "query": body.query,
            "region": body.region,
            "alert_id": body.alert_id,
            "errors": [],
        })
    except Exception as exc:
        logger.error("Agent invocation failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Agent request failed: {exc}")

    return {
        "response": result.get("response"),
        "context_used": result.get("datahub_context"),
        "freshness": result.get("freshness_result"),
        "model_health": result.get("model_health"),
        "lineage": result.get("lineage_result"),
    }