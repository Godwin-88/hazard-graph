"""HazardGraph — DataHub MCP Server integration bridge.

Provides a thin query layer over DataHub's metadata APIs that the
HazardGraph LangGraph agent uses to ground its responses in the
current metadata state of the pipeline.

In a full deployment this would connect to the DataHub MCP Server
via the Model Context Protocol. This bridge provides the same
interface using the DataHub Python SDK directly, so the agent
works even when the MCP server is not running.
"""

import logging
from typing import Optional

from hazarddatahub.entities import DATASETS, MODELS

logger = logging.getLogger(__name__)


def query_entities(
    entity_types: Optional[list[str]] = None,
    platform: str = "hazardgraph",
    include_lineage: bool = True,
    include_properties: bool = True,
) -> dict:
    """Query DataHub for entity metadata.

    Returns a dict with datasets and models matching the filter.
    This is a local implementation that reads from the canonical
    entity definitions; in production it would call the DataHub
    GraphQL API or MCP Server.
    """
    datasets = []
    for key, urn in DATASETS.items():
        if platform and platform not in urn:
            continue
        datasets.append({
            "key": key,
            "urn": urn,
            "type": "DATASET",
            "name": key,
            "properties": {"project": "HazardGraph"} if include_properties else {},
        })

    models = []
    for model_id, urn in MODELS.items():
        if platform and platform not in urn:
            continue
        models.append({
            "id": model_id,
            "urn": urn,
            "type": "ML_MODEL",
            "name": model_id,
            "properties": {"project": "HazardGraph"} if include_properties else {},
        })

    result = {"datasets": datasets, "models": models}
    if include_lineage:
        result["lineage_edges"] = len(_get_lineage_edges())
    return result


def get_lineage(entity_urn: str) -> list:
    """Return lineage edges for a given entity URN."""
    from hazarddatahub.lineage import LINEAGE_EDGES

    edges = []
    for upstream, downstream, description in LINEAGE_EDGES:
        if upstream == entity_urn or downstream == entity_urn:
            edges.append({
                "upstream": upstream,
                "downstream": downstream,
                "description": description,
            })
    return edges


def check_freshness(dataset_names: list[str]) -> dict:
    """Check freshness of upstream datasets.

    In production this reads last-updated timestamps from Neo4j
    DataSource nodes. Here we return a structured response that
    the agent can reason over.
    """
    freshness = {}
    for name in dataset_names:
        freshness[name] = {
            "status": "unknown",
            "last_updated": None,
            "max_age_hours": 168,
            "is_fresh": None,
        }
    return freshness


def get_model_health(model_ids: list[str]) -> dict:
    """Return model health (Brier score + BMA weight) for the given models.

    In production this reads from the model_performance PostgreSQL table.
    Here we return a structured response the agent can reason over.
    """
    health = {}
    for model_id in model_ids:
        health[model_id] = {
            "brier_score": None,
            "bma_weight": None,
            "status": "unknown",
            "needs_retraining": False,
        }
    return health


def _get_lineage_edges() -> list:
    """Return the full lineage edge list (lazy import to avoid cycles)."""
    from hazarddatahub.lineage import LINEAGE_EDGES

    return LINEAGE_EDGES
