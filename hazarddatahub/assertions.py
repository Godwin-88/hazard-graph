"""HazardGraph — DataHub data quality assertions.

These assertions are emitted to DataHub and evaluated on each pipeline run.
Failing assertions trigger alerts to the pipeline monitoring dashboard.
"""

import logging

logger = logging.getLogger(__name__)

QUALITY_ASSERTIONS = [
    {
        "name": "chirps_freshness",
        "description": "CHIRPS SPI data updated within 7 days",
        "entity": "chirps_spi_horn_of_africa",
        "type": "FRESHNESS",
        "max_age_hours": 170,
    },
    {
        "name": "bma_coverage",
        "description": "BMA score present for all 11 IGAD sub-regions",
        "entity": "bma_risk_scores_weekly",
        "type": "VOLUME",
        "min_rows": 11,
    },
    {
        "name": "bma_score_range",
        "description": "All BMA scores in valid range [0.0, 1.0]",
        "entity": "bma_risk_scores_weekly",
        "type": "COLUMN",
        "column": "bma_score",
        "constraint": "BETWEEN 0.0 AND 1.0",
    },
    {
        "name": "model_brier_threshold",
        "description": "No model Brier score exceeds 0.25 (underperformance threshold)",
        "entity": "all_model_outputs",
        "type": "CUSTOM",
        "query": "SELECT COUNT(*) FROM model_performance WHERE brier_score > 0.25",
        "expected": 0,
    },
    {
        "name": "gnn_ppo_model_exists",
        "description": "Trained GNN-PPO model weights exist and are < 30 days old",
        "entity": "gnn_ppo_alert_dispatch_agent",
        "type": "FRESHNESS",
        "max_age_hours": 720,
    },
]


def emit_assertions(client) -> None:
    """Emit all data quality assertions to DataHub.

    Uses DataHub's Assertion entity type with custom properties
    describing the check. In a production deployment these would
    be evaluated by DataHub's assertion runner.
    """
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import AssertionInfoClass, AssertionTypeClass

    for assertion in QUALITY_ASSERTIONS:
        # Build assertion URN
        assertion_urn = (
            f"urn:li:assertion:(hazardgraph,{assertion['name']})"
        )

        info = AssertionInfoClass(
            type=AssertionTypeClass.CUSTOM_SQL,
            customProperties={
                "name": assertion["name"],
                "description": assertion["description"],
                "entity": assertion["entity"],
                "assertion_type": assertion["type"],
                "max_age_hours": str(assertion.get("max_age_hours", "")),
                "min_rows": str(assertion.get("min_rows", "")),
                "column": assertion.get("column", ""),
                "constraint": assertion.get("constraint", ""),
                "query": assertion.get("query", ""),
                "expected": str(assertion.get("expected", "")),
                "project": "HazardGraph",
            },
        )

        mcp = MetadataChangeProposalWrapper(
            entityUrn=assertion_urn,
            aspect=info,
        )
        client.emit(mcp)

    logger.info("Emitted %d quality assertions to DataHub", len(QUALITY_ASSERTIONS))