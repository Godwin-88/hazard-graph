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


async def _write_regime_state(region_id: str, regime_name: str, posteriors: dict) -> None:
    """Persist a region's regime to Neo4j (property + IN_REGIME) and cache posteriors in Redis.

    Shared by both the trained-HMM path and the fallback path so the
    pipeline stays consistent regardless of HMM availability.
    """
    # Update Region node in Neo4j
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

    # Create/update IN_REGIME relationship by matching the HazardRegime id
    # (not name, which can differ in spacing, e.g. "Drought Onset" vs
    # "DroughtOnset" — a bug source that left regions unlinked before).
    regime_id_map = {
        "Baseline": "regime_baseline",
        "Drought Onset": "regime_drought_onset",
        "DroughtOnset": "regime_drought_onset",
        "Severe Drought": "regime_severe_drought",
        "SevereDrought": "regime_severe_drought",
        "Flood Watch": "regime_flood_watch",
        "FloodWatch": "regime_flood_watch",
        "Flood Emergency": "regime_flood_emergency",
        "FloodEmergency": "regime_flood_emergency",
    }
    regime_id = regime_id_map.get(str(regime_name).strip(), f"regime_{str(regime_name).strip().lower().replace(' ', '_')}")

    # Ensure the HazardRegime node exists with that id, then create IN_REGIME
    await neo4j_client.execute_write(
        """
        MERGE (hr:HazardRegime {id: $hid})
        SET hr.name = $regime_name
        WITH hr
        MATCH (r:Region {id: $rid})
        MERGE (r)-[rel:IN_REGIME]->(hr)
        SET rel.since = COALESCE(rel.since, $since),
            rel.updated_at = $updated_at
        """,
        {
            "hid": regime_id,
            "regime_name": regime_name,
            "rid": region_id,
            "since": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # Cache posteriors in Redis (1 hour TTL)
    cache_key = f"regime_posteriors:{region_id}"
    try:
        await redis_client.set(
            cache_key,
            json.dumps({"regime": regime_name, "posteriors": posteriors}),
            ttl=3600,
        )
    except Exception as exc:
        logger.warning("Failed to cache regime posteriors for %s: %s", region_id, exc)


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
    # Default posteriors per regime — used so the Regime Map always
    # reflects the region's current regime even when a real HMM cannot
    # be trained (e.g. insufficient panel data on a fresh deployment).
    _DEFAULT_POSTERIORS = {
        "Baseline":       {"Baseline": 0.78, "DroughtOnset": 0.10, "SevereDrought": 0.04, "FloodWatch": 0.05, "FloodEmergency": 0.03},
        "DroughtOnset":   {"Baseline": 0.15, "DroughtOnset": 0.62, "SevereDrought": 0.14, "FloodWatch": 0.05, "FloodEmergency": 0.04},
        "SevereDrought":  {"Baseline": 0.05, "DroughtOnset": 0.18, "SevereDrought": 0.68, "FloodWatch": 0.05, "FloodEmergency": 0.04},
        "FloodWatch":     {"Baseline": 0.14, "DroughtOnset": 0.05, "SevereDrought": 0.04, "FloodWatch": 0.62, "FloodEmergency": 0.15},
        "FloodEmergency": {"Baseline": 0.05, "DroughtOnset": 0.04, "SevereDrought": 0.03, "FloodWatch": 0.18, "FloodEmergency": 0.70},
    }

    try:
        # 1. Load HMM
        hmm = await load_or_train(region_id)

        # 1b. Get the current regime property so we always have a regime
        # even if model/posterior inference is unavailable.
        current_regime_row = await neo4j_client.execute_read(
            "MATCH (r:Region {id: $region_id}) RETURN r.current_regime AS regime",
            {"region_id": region_id},
        )
        current_regime = current_regime_row[0].get("regime") if current_regime_row else None

        if hmm is None:
            logger.warning("No HMM available for region %s — using current_regime posteriors", region_id)
            regime_name = current_regime or "Baseline"
            posteriors = _DEFAULT_POSTERIORS.get(regime_name, _DEFAULT_POSTERIORS["Baseline"])
            # Still update Neo4j + Redis so the pipeline stays consistent.
            await _write_regime_state(region_id, regime_name, posteriors)
            return {"region_id": region_id, "regime": regime_name, "posteriors": posteriors}

        # 2. Assemble panel data
        df = await assemble_panel(region_id, lookback_weeks=104)
        if df is None:
            logger.warning("No panel data for regime prediction in %s — using current_regime posteriors", region_id)
            regime_name = current_regime or "Baseline"
            posteriors = _DEFAULT_POSTERIORS.get(regime_name, _DEFAULT_POSTERIORS["Baseline"])
            # Still update Neo4j + Redis so the pipeline stays consistent.
            await _write_regime_state(region_id, regime_name, posteriors)
            return {"region_id": region_id, "regime": regime_name, "posteriors": posteriors}

        # 3. Predict regime
        regime_name, posteriors = hmm.predict_regime(df)
        logger.info("Region %s predicted regime: %s (posteriors: %s)", region_id, regime_name, posteriors)

        # 4-6. Persist regime (Neo4j property + IN_REGIME + Redis posteriors)
        await _write_regime_state(region_id, regime_name, posteriors)

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