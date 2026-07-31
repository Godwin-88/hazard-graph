"""HazardGraph — Risk assessment API router.

Implements the full compound risk scoring pipeline:
  1. Scoring service computes component + composite scores
  2. SDE simulation for all regions
  3. BMA posterior for each region
  4. Kelly alert prioritisation
  5. Redis caching (5 min TTL)
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from db.redis_client import redis_client
from models.ensemble.bma_engine import BMAEngine
from models.ensemble.kelly_prioritiser import (
    compute_kelly_priority,
    rank_alerts,
)
from risk.scoring_service import RegionRiskScore, compute_risk_scores
from models.stochastic.rainfall_sde import RainfallSDE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["risk"])

bma_engine = BMAEngine()
sde_engine = RainfallSDE()


@router.get("/risk/scores")
async def get_risk_scores():
    """Return all risk scores with full BMA + Kelly pipeline.

    Cached in Redis for 5 minutes TTL.
    """
    cache_key = "risk:scores"
    cached = await redis_client.get(cache_key)
    if cached is not None:
        return json.loads(cached)

    try:
        from db.neo4j_client import neo4j_client
        from db.postgres_client import async_session_factory
        from regime.regime_updater import update_all_regimes
        from models.postgres.risk import RiskHistory

        async with async_session_factory() as postgres_session:
            scoring_results = await compute_risk_scores(neo4j_client)
            sde_results = await sde_engine.run_all_regions(neo4j_client)

            bma_results: list = []
            for score_result in scoring_results:
                sde_result = sde_results.get(score_result.region_id, {})

                hmm_posteriors_cache = await redis_client.get(
                    f"regime_posteriors:{score_result.region_id}"
                )
                hmm_posteriors = (
                    json.loads(hmm_posteriors_cache).get("posteriors", {})
                    if hmm_posteriors_cache
                    else {}
                )

                bma_result = await bma_engine.compute_posterior(
                    region_id=score_result.region_id,
                    scoring_result=score_result,
                    sde_result=sde_result,
                    hmm_posteriors=hmm_posteriors,
                    neo4j_session=neo4j_client,
                    postgres_session=postgres_session,
                )
                bma_results.append(bma_result)

            kelly_alerts = rank_alerts(bma_results)

            regions_response = []
            for score_result in scoring_results:
                bma_match = next(
                    (b for b in bma_results if b.region_id == score_result.region_id),
                    None,
                )
                bma = bma_match if bma_match else None

                regions_response.append(
                    {
                        "id": score_result.region_id,
                        "name": score_result.name,
                        "country": score_result.country,
                        "score": score_result.score,
                        "bma_posterior": bma.posterior_risk if bma else 0.0,
                        "kelly_priority": compute_kelly_priority(bma) if bma else 0.0,
                        "confidence": bma.confidence if bma else "Low",
                        "delta": score_result.delta,
                        "alert_triggered": score_result.alert_triggered,
                        "current_regime": score_result.current_regime,
                        "components": score_result.components,
                        "vulnerability_multiplier": score_result.vulnerability_multiplier,
                    }
                )

            regions_in_alert = sum(
                1 for r in regions_response if r["alert_triggered"]
            )
            highest = max(regions_response, key=lambda r: r["score"])["name"] if regions_response else "N/A"
            avg_score = (
                sum(r["score"] for r in regions_response) / len(regions_response)
                if regions_response
                else 0.0
            )

            response = {
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "regions": regions_response,
                "summary": {
                    "regions_in_alert": regions_in_alert,
                    "highest_risk_region": highest,
                    "average_score": round(avg_score, 2),
                },
            }

            await redis_client.set(cache_key, json.dumps(response, default=str), ttl=300)
            return response

    except Exception as exc:
        logger.error("Risk scores computation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/risk/scores/{region_id}")
async def get_region_risk_score(region_id: str):
    """Return risk score for a specific region (not cached)."""
    try:
        from db.neo4j_client import neo4j_client
        from db.postgres_client import async_session_factory
        from models.ensemble.bma_engine import BMAEngine
        from models.stochastic.rainfall_sde import RainfallSDE

        bma_engine_local = BMAEngine()
        sde_engine_local = RainfallSDE()

        scoring_results = await compute_risk_scores(neo4j_client)
        score_result = next(
            (r for r in scoring_results if r.region_id == region_id), None
        )
        if score_result is None:
            raise HTTPException(status_code=404, detail=f"Region {region_id} not found")

        sde_result = await sde_engine_local.run_all_regions(neo4j_client)
        sde_data = sde_result.get(region_id, {})

        hmm_cache = await redis_client.get(f"regime_posteriors:{region_id}")
        hmm_posteriors = (
            json.loads(hmm_cache).get("posteriors", {})
            if hmm_cache
            else {}
        )

        async with async_session_factory() as postgres_session:
            bma_result = await bma_engine_local.compute_posterior(
                region_id=region_id,
                scoring_result=score_result,
                sde_result=sde_data,
                hmm_posteriors=hmm_posteriors,
                neo4j_session=neo4j_client,
                postgres_session=postgres_session,
            )

        return {
            "id": score_result.region_id,
            "name": score_result.name,
            "country": score_result.country,
            "score": score_result.score,
            "bma_posterior": bma_result.posterior_risk,
            "kelly_priority": compute_kelly_priority(bma_result),
            "confidence": bma_result.confidence,
            "delta": score_result.delta,
            "alert_triggered": score_result.alert_triggered,
            "current_regime": score_result.current_regime,
            "components": score_result.components,
            "vulnerability_multiplier": score_result.vulnerability_multiplier,
            "model_weights": bma_result.model_weights,
            "component_probabilities": bma_result.component_probabilities,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Region detail failed for %s: %s", region_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/risk/history/{region_id}")
async def get_region_history(region_id: str):
    """Return last 12 weeks of risk scores from PostgreSQL."""
    try:
        from db.postgres_client import async_session_factory
        from sqlalchemy import text

        async with async_session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT score, current_regime, computed_at "
                    "FROM risk_history "
                    "WHERE region_id = :rid "
                    "ORDER BY computed_at DESC "
                    "LIMIT 12"
                ),
                {"rid": region_id},
            )
            rows = result.fetchall()

        history = [
            {
                "date": row[2].isoformat() if row[2] else "",
                "score": round(row[0], 2) if row[0] else 0.0,
                "regime": row[1] or "Baseline",
            }
            for row in reversed(rows)
        ]

        return {
            "region_id": region_id,
            "history": history,
        }

    except Exception as exc:
        logger.error("History fetch failed for %s: %s", region_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/risk/trigger-scoring")
async def trigger_scoring():
    """Manual trigger for the full scoring pipeline.

    Admin-only endpoint (auth guard to be implemented).
    Runs the full pipeline and returns updated scores.
    """
    try:
        from db.neo4j_client import neo4j_client
        from db.postgres_client import async_session_factory
        from models.ensemble.bma_engine import BMAEngine
        from models.stochastic.rainfall_sde import RainfallSDE

        bma_engine_local = BMAEngine()
        sde_engine_local = RainfallSDE()

        scoring_results = await compute_risk_scores(neo4j_client)
        sde_results = await sde_engine_local.run_all_regions(neo4j_client)

        bma_results_local: list = []
        for score_result in scoring_results:
            sde_data = sde_results.get(score_result.region_id, {})

            hmm_cache = await redis_client.get(
                f"regime_posteriors:{score_result.region_id}"
            )
            hmm_posteriors = (
                json.loads(hmm_cache).get("posteriors", {})
                if hmm_cache
                else {}
            )

            async with async_session_factory() as postgres_session:
                bma_result = await bma_engine_local.compute_posterior(
                    region_id=score_result.region_id,
                    scoring_result=score_result,
                    sde_result=sde_data,
                    hmm_posteriors=hmm_posteriors,
                    neo4j_session=neo4j_client,
                    postgres_session=postgres_session,
                )
                bma_results_local.append(bma_result)

        await redis_client.set("risk:scores", "", ttl=0)

        return await get_risk_scores()

    except Exception as exc:
        logger.error("Manual scoring trigger failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))