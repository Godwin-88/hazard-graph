"""HazardGraph — Agent tool: query DataHub for metadata context."""

from hazarddatahub.mcp_bridge import query_entities


def query_datahub(params: dict) -> dict:
    """Query DataHub for entity metadata (datasets + models).

    Args:
        params: dict with optional keys:
            - entity_types: list[str] (e.g. ["DATASET", "ML_MODEL"])
            - platform: str filter
            - include_lineage: bool
            - include_properties: bool

    Returns:
        dict with datasets, models, and optional lineage edge count.
    """
    return query_entities(
        entity_types=params.get("entity_types"),
        platform=params.get("platform", "hazardgraph"),
        include_lineage=params.get("include_lineage", True),
        include_properties=params.get("include_properties", True),
    )