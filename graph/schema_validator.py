"""HazardGraph — Confirm graph schema on startup."""

import logging

from db.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

REQUIRED_LABELS = [
    "Region",
    "HazardType",
    "HazardRegime",
    "InterventionStrategy",
    "ForecastSignal",
    "RainfallSignal",
    "FoodPriceSignal",
    "IPCPhaseSignal",
    "StochasticSignal",
    "MLForecast",
    "BMAScore",
    "CausalEdge",
    "Alert",
    "DataSource",
    "HazardCluster",
]

REQUIRED_RELATIONSHIPS = [
    "MEASURED_IN",
    "CAUSES",
    "INCREASES_RISK_OF",
    "SOURCED_FROM",
    "TRIGGERED",
    "AFFECTS",
    "IN_REGIME",
    "RECOMMENDED_FOR",
    "CONFLICTS_WITH",
    "PRECEDES",
    "BELONGS_TO_CLUSTER",
    "SYSTEMICALLY_CRITICAL",
]


async def validate_schema() -> dict:
    """Check that all required node labels and relationship types exist in Neo4j.

    Returns a dict with missing_labels and missing_relationships.
    """
    result = {
        "valid": True,
        "missing_labels": [],
        "missing_relationships": [],
        "errors": [],
    }

    try:
        # Get existing labels
        labels_resp = await neo4j_client.execute_read(
            "CALL db.labels() YIELD label RETURN collect(label) AS labels"
        )
        existing_labels = set(labels_resp[0]["labels"]) if labels_resp else set()

        # Get existing relationship types
        rels_resp = await neo4j_client.execute_read(
            "CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) AS rels"
        )
        existing_rels = set(rels_resp[0]["rels"]) if rels_resp else set()

        # Check each required label
        for label in REQUIRED_LABELS:
            if label not in existing_labels:
                result["missing_labels"].append(label)

        # Check each required relationship
        for rel in REQUIRED_RELATIONSHIPS:
            if rel not in existing_rels:
                result["missing_relationships"].append(rel)

        result["valid"] = (
            len(result["missing_labels"]) == 0
            and len(result["missing_relationships"]) == 0
        )

        if not result["valid"]:
            logger.warning(
                "Schema validation incomplete. Missing labels: %s; Missing rels: %s",
                result["missing_labels"],
                result["missing_relationships"],
            )
        else:
            logger.info("Graph schema validation passed (%d labels, %d rel types)", len(existing_labels), len(existing_rels))

    except Exception as exc:
        result["valid"] = False
        result["errors"].append(str(exc))
        logger.error("Schema validation error: %s", exc)

    return result