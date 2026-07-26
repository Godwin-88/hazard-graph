"""HazardGraph — Causal edge writer.

Upserts CausalEdge nodes to Neo4j, soft-deletes previous runs,
and logs to PostgreSQL causal_runs table.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from db.neo4j_client import neo4j_client
from db.postgres_client import async_session_factory
from models.postgres.causal import CausalRun
from causal.varlingam_engine import CausalEdgeResult

logger = logging.getLogger(__name__)


async def write_causal_edges(
    edges: List[CausalEdgeResult],
    run_id: str,
) -> int:
    """Upsert CausalEdge nodes to Neo4j.

    Args:
        edges: List of CausalEdgeResult from VARLiNGAM discovery.
        run_id: Unique run identifier for tracking.

    Returns:
        Number of edges written.
    """
    if not edges:
        logger.info("No causal edges to write for run %s", run_id)
        return 0

    region_id = edges[0].region_id
    written = 0

    try:
        # 1. Upsert each edge
        for edge in edges:
            edge_id = f"{edge.region_id}_{edge.source_variable}_{edge.target_variable}_lag{edge.lag_weeks}"
            # Hash to keep ID length manageable
            edge_id = f"ce_{hashlib.md5(edge_id.encode()).hexdigest()[:16]}"

            lag_days = edge.lag_weeks * 7

            query = """
            MERGE (e:CausalEdge {id: $edge_id})
            SET e.source_variable = $source_variable,
                e.target_variable = $target_variable,
                e.weight = $weight,
                e.lag_days = $lag_days,
                e.lag_weeks = $lag_weeks,
                e.method = 'VARLiNGAM',
                e.p_value = $p_value,
                e.discovered_at = $discovered_at,
                e.run_id = $run_id,
                e.region_id = $region_id,
                e.active = true
            """
            params = {
                "edge_id": edge_id,
                "source_variable": edge.source_variable,
                "target_variable": edge.target_variable,
                "weight": edge.weight,
                "lag_days": lag_days,
                "lag_weeks": edge.lag_weeks,
                "p_value": edge.p_value,
                "discovered_at": edge.discovered_at.isoformat(),
                "run_id": run_id,
                "region_id": edge.region_id,
            }
            await neo4j_client.execute_write(query, params)
            written += 1

        # 2. Soft-delete previous edges from same region not in this run
        deactivate_query = """
        MATCH (e:CausalEdge {region_id: $region_id, active: true})
        WHERE e.run_id <> $run_id
        SET e.active = false
        RETURN count(e) AS deactivated
        """
        deactivated_result = await neo4j_client.execute_write(
            deactivate_query,
            {"region_id": region_id, "run_id": run_id},
        )
        deactivated = deactivated_result[0]["deactivated"] if deactivated_result else 0

        # 3. Log to PostgreSQL causal_runs table
        try:
            async with async_session_factory() as session:
                causal_run = CausalRun(
                    id=uuid.UUID(run_id) if len(run_id) == 36 else uuid.uuid4(),
                    run_name=f"VARLiNGAM_{region_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                    method="VARLiNGAM",
                    region_id=region_id,
                    signal_types=",".join(sorted(set(e.source_variable for e in edges))),
                    num_edges_discovered=written,
                    execution_time_seconds=0.0,  # Will be updated by caller
                    status="completed",
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                )
                session.add(causal_run)
                await session.commit()
        except Exception as exc:
            logger.error("Failed to log causal run to PostgreSQL: %s", exc)

        logger.info(
            "Causal edges written: %d active, %d deactivated for region %s (run %s)",
            written, deactivated, region_id, run_id,
        )

    except Exception as exc:
        logger.error("Failed to write causal edges for run %s: %s", run_id, exc)
        # Log failed run
        try:
            async with async_session_factory() as session:
                causal_run = CausalRun(
                    id=uuid.uuid4(),
                    run_name=f"VARLiNGAM_{region_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                    method="VARLiNGAM",
                    region_id=region_id,
                    status="failed",
                    error_message=str(exc),
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                )
                session.add(causal_run)
                await session.commit()
        except Exception:
            pass

    return written