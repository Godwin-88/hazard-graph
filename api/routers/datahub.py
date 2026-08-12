"""HazardGraph — DataHub integration API routes.

GET  /api/v1/datahub/lineage/{alert_id}  — trace alert provenance
GET  /api/v1/datahub/model-health        — all 14 models with Brier/BMA
GET  /api/v1/datahub/pipeline-freshness  — upstream dataset freshness
POST /api/v1/datahub/sync                — trigger full DataHub sync
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from auth.jwt_service import get_current_user
from hazarddatahub.client import HazardGraphDataHubClient, get_datahub_client
from hazarddatahub.lineage import trace_alert_lineage
from hazarddatahub.model_registry import MODEL_REGISTRY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/datahub", tags=["datahub"])


@router.get("/lineage/{alert_id}")
async def get_alert_lineage(
    alert_id: str,
    _user=Depends(get_current_user),
    client: HazardGraphDataHubClient = Depends(get_datahub_client),
):
    """Trace the complete provenance of a dispatched alert.

    Returns the 8-step lineage chain from raw satellite data to SMS.
    """
    return trace_alert_lineage(alert_id, client)


@router.get("/model-health")
async def get_model_health(_user=Depends(get_current_user)):
    """Return all 14 models with their current Brier scores,
    BMA weights, last training timestamp, and DataHub entity URNs.
    """
    from hazarddatahub.entities import MODELS

    models = []
    for spec in MODEL_REGISTRY:
        d = {
            "id": spec.id,
            "name": spec.name,
            "urn_name": spec.urn_name,
            "category": spec.category,
            "technique": spec.technique,
            "output_description": spec.output_description,
            "update_frequency": spec.update_frequency,
            "brier_score": spec.brier_score,
            "bma_weight": spec.bma_weight,
            "upstream_datasets": spec.upstream_datasets,
            "datahub_urn": MODELS.get(spec.id),
        }
        models.append(d)
    return {"models": models}


@router.get("/pipeline-freshness")
async def get_pipeline_freshness(_user=Depends(get_current_user)):
    """Return freshness status of all upstream datasets.

    Flags any dataset that has not been updated within expected window.
    """
    from agents.tools.freshness_check_tool import check_freshness

    result = await check_freshness([
        "chirps_spi_horn_of_africa",
        "modis_ndvi_horn_of_africa",
        "wfp_food_prices_igad",
        "ipc_phase_reports_igad",
        "icpac_rss_alerts",
    ])
    return {"datasets": result}


@router.post("/sync")
async def sync_to_datahub(_user=Depends(get_current_user)):
    """Trigger a full sync of HazardGraph metadata to DataHub:

    - Register all 14 models
    - Emit all lineage edges
    - Push current Brier scores and BMA weights
    - Assert data quality checks
    """
    import asyncio

    from hazarddatahub.sync_job import sync_all

    try:
        # sync_all is synchronous (DataHub REST emitter) — run in a thread
        return await asyncio.to_thread(sync_all)
    except Exception as exc:
        logger.error("DataHub sync failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"DataHub sync failed: {exc}")
