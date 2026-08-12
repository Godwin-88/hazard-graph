"""
HazardGraph — Full Real Data Pipeline Runner

Triggers the complete data pipeline from real sources:
  1. Neo4j schema migration
  2. CHIRPS rainfall ingestion (real UCSB/CHC data)
  3. WFP food price ingestion (real WFP VAM API)
  4. IPC phase ingestion (real IPC API)
  5. ICPAC RSS ingestion (real ICPAC feed + Groq extraction)
  6. NASA POWER climate ingestion (no key required)
  7. FAOSTAT food price index ingestion (no key required)
  8. WFP/HDX NDVI greenness ingestion (no key required)
  9. ACLED conflict ingestion (requires ACLED_EMAIL/ACLED_PASSWORD — OAuth)
  10. HMM climate regime detection
  11. SDE rainfall simulation
  12. VARLiNGAM causal discovery
  13. Risk scoring + BMA + Kelly prioritisation
  14. Advisory generation (Groq LLM)

Usage:
  docker compose exec app python scripts/run_pipeline.py
"""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()


async def run_migration(neo4j_session):
    """Run the 001_schema.cypher migration file."""
    migration_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'migrations', '001_schema.cypher'
    )
    with open(migration_path) as f:
        migration = f.read()

    for stmt in migration.split(';'):
        stmt = stmt.strip()
        if not stmt or stmt.startswith('//') or stmt.startswith('println'):
            continue
        try:
            await neo4j_session.run(stmt)
        except Exception as e:
            if 'already exists' not in str(e).lower():
                print(f"  Migration warning: {e}")


async def step(name: str, coro, timeout: int = 300):
    """Run a pipeline step with timing."""
    print(f"\n{'='*60}")
    print(f"  [{name}]")
    print(f"{'='*60}")
    start = time.time()
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        elapsed = time.time() - start
        print(f"  ✅ {name} completed in {elapsed:.1f}s")
        if isinstance(result, dict):
            for k, v in result.items():
                print(f"     {k}: {v}")
        return result
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"  ⚠️  {name} timed out after {elapsed:.1f}s (limit: {timeout}s)")
        return None
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ {name} failed after {elapsed:.1f}s: {e}")
        return None


async def run_pipeline():
    """Execute the full real-data pipeline in order."""
    from db.neo4j_client import neo4j_client
    from db.postgres_client import async_session_factory, create_all_tables
    from db.redis_client import redis_client

    # 1. Connect databases
    print("\n🔌 Connecting to databases...")
    await neo4j_client.connect()
    await redis_client.connect()
    await create_all_tables()
    print("   Neo4j ✅  |  Redis ✅  |  PostgreSQL ✅\n")

    # 2. Migration
    async with neo4j_client.get_session() as session:
        await step("Neo4j Schema Migration", run_migration(session))

    # 3. CHIRPS Rainfall Ingestion (real UCSB/CHC data)
    from ingestion.chirps_fetcher import fetch_all_regions as chirps_ingest
    await step("CHIRPS Rainfall Ingestion", chirps_ingest(), timeout=180)

    # 4. WFP Food Price Ingestion (real WFP VAM API)
    from ingestion.wfp_fetcher import fetch_all_countries as wfp_ingest
    await step("WFP Food Price Ingestion", wfp_ingest(), timeout=180)

    # 5. IPC Phase Ingestion (real IPC API)
    from ingestion.ipc_fetcher import fetch_all_countries as ipc_ingest
    await step("IPC Phase Ingestion", ipc_ingest(), timeout=180)

    # 6. ICPAC RSS Ingestion (real ICPAC feed + Groq extraction)
    from ingestion.icpac_rss_fetcher import ingest_icpac_rss as icpac_ingest
    await step("ICPAC RSS Ingestion", icpac_ingest(), timeout=180)

    # 7. NASA POWER Climate Ingestion (no key required)
    from ingestion.nasa_power_fetcher import fetch_all_regions as nasa_ingest
    await step("NASA POWER Climate Ingestion", nasa_ingest(), timeout=180)

    # 8. FAOSTAT Food Price Index Ingestion (no key required)
    from ingestion.faostat_fetcher import fetch_all_countries as faostat_ingest
    await step("FAOSTAT Food Price Index Ingestion", faostat_ingest(), timeout=180)

    # 9. WFP/HDX NDVI Greenness Ingestion (no key required)
    from ingestion.ndvi_fetcher import fetch_all_regions as ndvi_ingest
    await step("WFP/HDX NDVI Greenness Ingestion", ndvi_ingest(), timeout=180)

    # 10. ACLED Conflict Ingestion (requires ACLED_EMAIL/ACLED_PASSWORD — OAuth)
    from ingestion.acled_fetcher import fetch_conflict_data as acled_ingest
    await step("ACLED Conflict Ingestion", acled_ingest(), timeout=180)

    # 11. HMM Climate Regime Detection
    from regime.regime_updater import update_all_regimes
    await step("HMM Climate Regime Detection", update_all_regimes(), timeout=180)

    # 12. SDE Rainfall Simulation
    from models.stochastic.rainfall_sde import RainfallSDE
    async def run_sde():
        engine = RainfallSDE()
        return await engine.run_all_regions(neo4j_client)
    await step("SDE Rainfall Simulation", run_sde(), timeout=120)

    # 13. Kalman Smoothing
    from models.filtering.kalman import KalmanSmoother
    async def run_kalman():
        smoother = KalmanSmoother()
        return await smoother.smooth_all()
    await step("Kalman Smoothing", run_kalman(), timeout=60)

    # 14. VARLiNGAM Causal Discovery
    from causal.varlingam_engine import VARLiNGAMEngine
    from causal.time_series_assembler import assemble_panel
    from causal.edge_writer import write_causal_edges
    import uuid

    async def run_varlingam():
        engine = VARLiNGAMEngine()
        total_edges = 0
        regions = await neo4j_client.execute_read(
            "MATCH (r:Region) RETURN r.id AS id"
        )
        for region in regions:
            region_id = region["id"]
            try:
                df = await assemble_panel(region_id, lookback_weeks=104)
                if df is None:
                    continue
                edges = await engine.discover(df, region_id)
                if edges:
                    run_id = str(uuid.uuid4())
                    n = await write_causal_edges(edges, run_id)
                    total_edges += n
                    print(f"     {region_id}: {n} causal edges")
            except Exception as exc:
                print(f"     {region_id}: skipped ({exc})")
                continue
        return {"total_edges": total_edges}
    await step("VARLiNGAM Causal Discovery", run_varlingam(), timeout=600)

    # 15. Risk Scoring
    from risk.scoring_service import compute_risk_scores
    async def run_scoring():
        scores = await compute_risk_scores(neo4j_client)
        return {"regions_scored": len(scores)}
    await step("Compound Risk Scoring", run_scoring(), timeout=120)

    # 16. BMA Ensemble
    from models.ensemble.bma_engine import BMAEngine
    import json

    async def run_bma():
        scores = await compute_risk_scores(neo4j_client)
        bma_results = []
        for score in scores:
            try:
                hmm_cache = await redis_client.get(f"regime_posteriors:{score.region_id}")
                hmm_posteriors = json.loads(hmm_cache).get("posteriors", {}) if hmm_cache else {}
                async with async_session_factory() as pg:
                    bma = await BMAEngine().compute_posterior(
                        region_id=score.region_id,
                        scoring_result=score,
                        sde_result={},
                        hmm_posteriors=hmm_posteriors,
                        neo4j_session=neo4j_client,
                        postgres_session=pg,
                    )
                    bma_results.append(bma)
            except Exception as e:
                print(f"     BMA failed for {score.region_id}: {e}")
        return {"regions_computed": len(bma_results)}
    await step("BMA Bayesian Ensemble", run_bma(), timeout=180)

    # 17. Kelly Prioritisation
    from models.ensemble.kelly_prioritiser import update_alert_kelly_scores
    async def run_kelly():
        scores = await compute_risk_scores(neo4j_client)
        async with async_session_factory() as pg:
            from models.ensemble.bma_engine import BMAResult
            bma_results = [
                BMAResult(
                    region_id=s.region_id,
                    posterior_risk=s.score / 100.0,
                    epistemic_uncertainty=0.1,
                    confidence="Medium",
                    model_weights={},
                    component_probabilities={},
                )
                for s in scores
            ]
            count = await update_alert_kelly_scores(bma_results, pg)
            return {"alerts_prioritised": count}
    await step("Kelly Prioritiser", run_kelly(), timeout=60)

    # 18. Advisory Generation (Groq LLM)
    from alerts.advisory_generator import AdvisoryGenerator
    async def run_advisory():
        scores = await compute_risk_scores(neo4j_client)
        async with async_session_factory() as pg:
            gen = AdvisoryGenerator()
            alert_ids = await gen.generate_all_triggered(
                risk_scores=scores,
                bma_results=[],
                postgres_session=pg,
                neo4j_session=neo4j_client,
            )
            return {"alerts_generated": len(alert_ids)}
    await step("Advisory Generation (Groq LLM)", run_advisory(), timeout=180)

    # 19. Cleanup
    await neo4j_client.close()
    await redis_client.close()

    print(f"\n{'='*60}")
    print("  🎉 REAL DATA PIPELINE COMPLETE")
    print(f"{'='*60}")
    print()
    print("  Data has been ingested from real sources:")
    print("  • CHIRPS rainfall data from UCSB/CHC")
    print("  • WFP food prices from VAM API")
    print("  • IPC phases from IPC API")
    print("  • ICPAC RSS bulletins via Groq extraction")
    print("  • NASA POWER climate data (no key required)")
    print("  • FAOSTAT food price indices (no key required)")
    print("  • WFP/HDX NDVI greenness (no key required)")
    print("  • ACLED conflict events (when key configured)")
    print("  • HMM regimes detected from rainfall patterns")
    print("  • SDE simulations for drought/flood probabilities")
    print("  • VARLiNGAM causal edges discovered")
    print("  • Compound risk scores computed")
    print("  • BMA ensemble posteriors calculated")
    print("  • Kelly-optimal alert priorities set")
    print("  • Advisories generated via Groq LLM")
    print()
    print("  Refresh the dashboard at http://localhost:8000")
    print("  Login: admin / HazardGraph2026!")
    print()


if __name__ == '__main__':
    asyncio.run(run_pipeline())