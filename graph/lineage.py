"""HazardGraph — DataSource lineage writer.

Writes SOURCED_FROM relationships between graph nodes and their
originating DataSource nodes.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from db.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


async def record_lineage(
    node_id: str,
    source_id: str,
) -> None:
    """Create a SOURCED_FROM relationship from a node to a DataSource.

    Uses parameterised Cypher to avoid injection risks.
    """
    query = """
    MATCH (n {id: $node_id})
    MATCH (ds:DataSource {id: $source_id})
    MERGE (n)-[:SOURCED_FROM]->(ds)
    """
    await neo4j_client.execute_write(query, {"node_id": node_id, "source_id": source_id})
    logger.info("Lineage recorded: %s → SOURCED_FROM → %s", node_id, source_id)


async def get_lineage(source_id: Optional[str] = None) -> list:
    """Retrieve all DataSource nodes, optionally filtered by source_id.

    Returns a list of dicts with DataSource properties.
    """
    if source_id:
        query = """
        MATCH (ds:DataSource {id: $source_id})
        RETURN ds.id AS id, ds.name AS name, ds.url AS url,
               ds.ingested_at AS ingested_at, ds.record_count AS record_count,
               ds.hash AS hash
        """
        params = {"source_id": source_id}
    else:
        query = """
        MATCH (ds:DataSource)
        RETURN ds.id AS id, ds.name AS name, ds.url AS url,
               ds.ingested_at AS ingested_at, ds.record_count AS record_count,
               ds.hash AS hash
        ORDER BY ds.ingested_at DESC
        """
        params = {}

    return await neo4j_client.execute_read(query, params)


async def update_data_source_stats(
    source_id: str,
    record_count: int,
    hash_value: str,
) -> None:
    """Update record_count and hash for a DataSource after ingestion."""
    query = """
    MATCH (ds:DataSource {id: $source_id})
    SET ds.record_count = $record_count,
        ds.hash = $hash_value,
        ds.ingested_at = $ingested_at
    RETURN ds.id AS id, ds.record_count AS record_count
    """
    params = {
        "source_id": source_id,
        "record_count": record_count,
        "hash_value": hash_value,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    await neo4j_client.execute_write(query, params)
    logger.info("Updated DataSource %s stats: %d records", source_id, record_count)