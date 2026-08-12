"""HazardGraph — Agent tool: trace alert lineage back to source data."""

from hazarddatahub.lineage import trace_alert_lineage


def trace_lineage(alert_id: str) -> dict:
    """Trace a dispatched alert's complete provenance chain.

    Alert → Kelly → BMA → [14 model contributions] → [raw data sources]

    Args:
        alert_id: The dispatched alert identifier.

    Returns:
        dict with the 8-step lineage chain.
    """
    return trace_alert_lineage(alert_id)