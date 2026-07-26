"""HazardGraph — Regime updater for all regions.

Loads fitted HMM models, predicts current regime per region,
updates Neo4j Region nodes, and caches posteriors in Redis.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from db.neo4j_client import neo4j_client
from db.postgres_client import async_session_factory
from db.redis_client import redis_client
from causal.time_series_assembler import assemble_panel
from models.regime.hmm_trainer import load_or_train
from models.postgres.jobs import JobRun

logger = logging.getLogger(__name__)


async def update_region_regime(region_id: str) -> Optional[dict]:
    """Update the climate regime for a single region.

    Steps:
    1. Load or train HMM for the region
    2. Assemble recent panel data
    3. Predict current regime
    4. Update Neo4j Region node
    5. Create/update IN_REGIME relationship
    6. Cache posteriors in Redis

    Returns:
        Dict with regime info, or None on failure.
    """
    try:
        # 1. Load HMM
        hmm = await load_or_train(region_id)
        if hmm is None:
            logger.warning("No HMM available for region %s", region_id)
            return None

        # 2. Assemble panel data
        df = await assemble_panel(region_id, lookback_weeks=104)
        if df is None:
            logger.warning("No panel data for regime prediction in %s", region_id)
            return None

        # 3. Predict regime
        regime_name, posteriors = hmm.predict_regime(df)
        logger.info("Region %s predicted regime: %s (posteriors: %s)", region_id, regime_name, posteriors)

        # 4. Update Region node in Neo4j
        update_query = """
        MATCH (r:Region {id: $region_id})
        SET r.current_regime = $regime_name,
            r.updated_at = $updated_at
        RETURN r.id AS id, r.name AS name
        """
        await neo4j_client.execute_write(update_query, {
            "region_id": region_id,
            "regime_name": regime_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        # 5. Create/update IN_REGIME relationship
        # First, find or create the HazardRegime node
        regime_query = """
        MERGE (hr:HazardRegime {name: $regime_name})
        SET hr.updated_at = $updated_at
        RETURN hr.id AS id, hr.name AS name
        """
        regime_result = await neo4j_client.execute_write(regime_query, {
            "regime_name": regime_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        # Create IN_REGIME relationship
        rel_query = """
        MATCH (r:Region {id: $region_id})
        MATCH (hr:HazardRegime {name: $regime_name})
        MERGE (r)-[rel:IN_REGIME]->(hr)
        SET rel.since = COALESCE(rel.since, $since),
            rel.updated_at = $updated_at
        """
        await neo4j_client.execute_write(rel_query, {
            "region_id": region_id,
            "regime_name": regime_name,
            "since": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        # 6. Cache posteriors in Redis (1 hour TTL)
        cache_key = f"regime_posteriors:{region_id}"
        try:
            await redis_client.set(
                cache_key,
                json.dumps({"regime": regime_name, "posteriors": posteriors}),
                ttl=3600,
            )
        except Exception as exc:
            logger.warning("Failed to cache regime posteriors for %s: %s", region_id, exc)

        return {
            "region_id": region_id,
            "regime": regime_name,
            "posteriors": posteriors,
        }

    except Exception as exc:
        logger.error("Failed to update regime for region %s: %s", region_id, exc)
        return None


async def update_all_regimes() -> dict:
    """Update climate regimes for all Region nodes in Neo4j.

    Returns summary dict with counts.
    """
    summary = {"total": 0, "updated": 0, "failed": 0, "skipped": 0}

    try:
        # Get all region IDs from Neo4j
        regions_query = """
        MATCH (r:Region)
        RETURN r.id AS id, r.name AS name
        ORDER BY r.name
        """
        regions = await neo4j_client.execute_read(regions_query)

        summary["total"] = len(regions)
        logger.info("Updating regimes for %d regions", len(regions))

        for region in regions:
            region_id = region["id"]
            try:
                result = await update_region_regime(region_id)
                if result:
                    summary["updated"] += 1
                else:
                    summary["skipped"] += 1
            except Exception as exc:
                summary["failed"] += 1
                logger.error("Regime update failed for %s: %s", region_id, exc)

        # Log to job_runs table
        try:
            async with async_session_factory() as session:
                run = JobRun(
                    job_name="hmm_regime_update",
                    status="completed",
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    records_processed=summary["updated"],
                )
                session.add(run)
                await session.commit()
        except Exception as exc:
            logger.error("Failed to log regime update run: %s", exc)

    except Exception as exc:
        logger.error("update_all_regimes failed: %s", exc)
        summary["failed"] = summary["total"]

    logger.info(
        "Regime update complete: %d updated, %d skipped, %d failed out of %d",
        summary["updated"], summary["skipped"], summary["failed"], summary["total"],
    )
    return summary