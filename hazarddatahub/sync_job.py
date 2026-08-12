"""HazardGraph — Full DataHub registry sync job.

Runs on a schedule (weekly Monday) and on-demand via the
POST /api/v1/datahub/sync endpoint. Registers all datasets,
models, lineage edges, and quality assertions with DataHub.
"""

import logging

from hazarddatahub.client import HazardGraphDataHubClient

logger = logging.getLogger(__name__)


def sync_all(client: HazardGraphDataHubClient | None = None) -> dict:
    """Run the full DataHub metadata sync.

    Returns a summary dict with counts of registered entities.
    """
    if client is None:
        client = HazardGraphDataHubClient()

    from hazarddatahub.dataset_registry import register_all_datasets
    from hazarddatahub.model_registry import register_all_models
    from hazarddatahub.lineage import emit_full_lineage, LINEAGE_EDGES
    from hazarddatahub.assertions import emit_assertions, QUALITY_ASSERTIONS

    register_all_datasets(client)
    register_all_models(client)
    emit_full_lineage(client)
    emit_assertions(client)

    summary = {
        "status": "synced",
        "datasets": 9,
        "models": 14,
        "lineage_edges": len(LINEAGE_EDGES),
        "assertions": len(QUALITY_ASSERTIONS),
    }
    logger.info("DataHub sync complete: %s", summary)
    return summary