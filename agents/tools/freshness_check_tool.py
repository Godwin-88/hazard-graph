"""HazardGraph — Agent tool: check upstream dataset freshness.

Reads last ingestion timestamps from Neo4j DataSource nodes and
flags any dataset whose last update exceeds its expected cadence.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Expected max age (hours) for each upstream dataset
FRESHNESS_THRESHOLDS = {
    "chirps_spi_horn_of_africa": 170,   # ~7 days
    "modis_ndvi_horn_of_africa": 170,   # ~7 days
    "wfp_food_prices_igad": 170,        # ~7 days
    "ipc_phase_reports_igad": 720,      # ~30 days
    "icpac_rss_alerts": 72,             # ~3 days
}


async def check_freshness(dataset_names: list[str]) -> dict:
    """Check whether upstream datasets are fresh.

    Reads DataSource node ingested_at timestamps from Neo4j. If the
    DataSource node is missing, returns status 'unknown'.

    Args:
        dataset_names: List of dataset names to check.

    Returns:
        dict mapping dataset name → freshness status dict.
    """
    result = {}

    # Try to read real ingested_at timestamps from Neo4j
    from db.neo4j_client import neo4j_client

    for name in dataset_names:
        threshold_hours = FRESHNESS_THRESHOLDS.get(name, 168)
        try:
            rows = await neo4j_client.execute_read(
                "MATCH (ds:DataSource) "
                "WHERE ds.id CONTAINS $name OR ds.name CONTAINS $name "
                "RETURN ds.id AS id, ds.name AS name, ds.ingested_at AS ingested_at "
                "ORDER BY ds.ingested_at DESC LIMIT 1",
                {"name": name},
            )
        except Exception as exc:
            logger.warning("Freshness check failed for %s: %s", name, exc)
            rows = []

        if not rows:
            result[name] = {
                "status": "unknown",
                "last_updated": None,
                "max_age_hours": threshold_hours,
                "is_fresh": None,
                "note": "No DataSource node found in Neo4j for this dataset",
            }
            continue

        row = rows[0]
        ingested_at = row.get("ingested_at")
        if ingested_at is None:
            result[name] = {
                "status": "unknown",
                "last_updated": None,
                "max_age_hours": threshold_hours,
                "is_fresh": None,
                "note": "DataSource node exists but has no ingested_at timestamp",
            }
            continue

        # ingested_at may be a Neo4j datetime object or ISO string
        try:
            if hasattr(ingested_at, "to_native"):
                last_updated = ingested_at.to_native()
            elif isinstance(ingested_at, str):
                last_updated = datetime.fromisoformat(
                    ingested_at.replace("Z", "+00:00")
                )
            else:
                last_updated = ingested_at
        except Exception:
            last_updated = None

        if last_updated is None:
            result[name] = {
                "status": "unknown",
                "last_updated": None,
                "max_age_hours": threshold_hours,
                "is_fresh": None,
                "note": "Could not parse ingested_at timestamp",
            }
            continue

        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)

        age_hours = (datetime.now(timezone.utc) - last_updated).total_seconds() / 3600
        is_fresh = age_hours <= threshold_hours

        result[name] = {
            "status": "fresh" if is_fresh else "stale",
            "last_updated": last_updated.isoformat(),
            "age_hours": round(age_hours, 1),
            "max_age_hours": threshold_hours,
            "is_fresh": is_fresh,
        }

    return result