"""HazardGraph — Full ML pipeline DAG definition.

Builds the complete pipeline DAG with all ingestion, processing,
scoring, and advisory generation nodes wired together.
"""

import logging

from pipeline.dag_executor import AsyncDAGExecutor

logger = logging.getLogger(__name__)


async def build_pipeline(
    neo4j_session=None,
    postgres_session=None,
    redis_client=None,
) -> AsyncDAGExecutor:
    """Build and return the full HazardGraph ML pipeline DAG.

    Core ingestion sources wired into the DAG:
      chirps (CHIRPS rainfall)  ─┐
      wfp    (WFP food prices)  ─┤→ kalman_smooth → sde_simulate ─┐
      ipc    (IPC phases)       ─┘                                 │
      icpac  (ICPAC RSS alerts) ───────→ hmm_update  ──────────────┤
                                                                   │
      varlingam_discover ─────────────────────────────────────────→┤
                                                                   ↓
                                                         bma_compute
                                                                   ↓
                                                         kelly_prioritise
                                                                   ↓
                                                         advisory_generate
                                                                   ↓
                                                         (await approval)
                                                                   ↓
                                                         sms_dispatch

    Additional real-data fetchers (NASA POWER climate, FAOSTAT food
    price indices, WFP/HDX NDVI, ACLED conflict) run as scheduled jobs
    via scheduler/jobs.py and write their own signal nodes, which the
    scoring node's Neo4j query consumes through OPTIONAL MATCH.
    """
    dag = AsyncDAGExecutor()

    # ── Ingestion nodes (batch 0 — no dependencies) ────────
    # Wrap in defensive handlers so a transient network / API failure
    # logs a warning and returns an empty summary rather than being
    # recorded as a hard node error (which cascades to downstream skips).
    from ingestion.chirps_fetcher import fetch_all_regions as chirps_fn
    from ingestion.wfp_fetcher import fetch_all_countries as wfp_fn
    from ingestion.ipc_fetcher import fetch_all_countries as ipc_fn
    from ingestion.icpac_rss_fetcher import ingest_icpac_rss as icpac_fn

    async def chirps_wrapper(**kwargs):
        try:
            return await chirps_fn()
        except Exception as exc:
            logger.warning("chirps ingestion failed (continuing): %s", exc)
            return {"written": 0, "skipped": True}

    async def wfp_wrapper(**kwargs):
        try:
            return await wfp_fn()
        except Exception as exc:
            logger.warning("wfp ingestion failed (continuing): %s", exc)
            return {"written": 0, "skipped": True}

    async def ipc_wrapper(**kwargs):
        try:
            return await ipc_fn()
        except Exception as exc:
            logger.warning("ipc ingestion failed (continuing): %s", exc)
            return {"written": 0, "skipped": True}

    async def icpac_wrapper(**kwargs):
        try:
            return await icpac_fn()
        except Exception as exc:
            logger.warning("icpac ingestion failed (continuing): %s", exc)
            return {"written": 0, "skipped": True}

    dag.add_node("chirps", chirps_wrapper, timeout_seconds=120)
    dag.add_node("wfp", wfp_wrapper, timeout_seconds=60)
    dag.add_node("ipc", ipc_wrapper, timeout_seconds=60)
    dag.add_node("icpac", icpac_wrapper, timeout_seconds=60)

    # ── Processing nodes (batch 1 — depend on ingestion) ───
    from models.filtering.kalman import KalmanSmoother

    async def kalman_wrapper(**kwargs):
        smoother = KalmanSmoother()
        return await smoother.smooth_all()

    dag.add_node("kalman", kalman_wrapper, depends_on=["chirps"], timeout_seconds=30)

    from models.stochastic.rainfall_sde import RainfallSDE

    async def sde_wrapper(**kwargs):
        engine = RainfallSDE()
        return await engine.run_all_regions(neo4j_session)

    dag.add_node("sde", sde_wrapper, depends_on=["kalman"], timeout_seconds=60)

    from regime.regime_updater import update_all_regimes

    async def hmm_wrapper(**kwargs):
        return await update_all_regimes()

    dag.add_node("hmm", hmm_wrapper, depends_on=["chirps", "wfp", "ipc"], timeout_seconds=120)

    from causal.varlingam_engine import VARLiNGAMEngine
    from causal.time_series_assembler import assemble_panel
    from causal.edge_writer import write_causal_edges
    import uuid

    async def varlingam_wrapper(**kwargs):
        engine = VARLiNGAMEngine()
        total_edges = 0
        regions = await neo4j_session.execute_read(
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
            except Exception as exc:
                logger.error("VARLiNGAM failed for %s: %s", region_id, exc)
                continue
        return {"total_edges": total_edges}

    dag.add_node(
        "varlingam",
        varlingam_wrapper,
        depends_on=["chirps", "wfp", "ipc"],
        timeout_seconds=600,
    )

    # ── Scoring nodes (batch 2 — depend on processing) ─────
    from risk.scoring_service import compute_risk_scores

    async def scoring_wrapper(**kwargs):
        return await compute_risk_scores(neo4j_session)

    dag.add_node(
        "scoring",
        scoring_wrapper,
        depends_on=["sde", "hmm", "varlingam"],
        timeout_seconds=60,
    )

    from models.ensemble.bma_engine import BMAEngine

    async def bma_wrapper(**kwargs):
        scoring_results = kwargs.get("scoring_results") or []
        sde_results = kwargs.get("sde_results") or {}
        bma_results = []
        for score in scoring_results:
            sde_data = sde_results.get(score.region_id, {})
            hmm_cache = await redis_client.get(
                f"regime_posteriors:{score.region_id}"
            ) if redis_client else None
            import json
            hmm_posteriors = (
                json.loads(hmm_cache).get("posteriors", {})
                if hmm_cache else {}
            )
            bma = await BMAEngine().compute_posterior(
                region_id=score.region_id,
                scoring_result=score,
                sde_result=sde_data,
                hmm_posteriors=hmm_posteriors,
                neo4j_session=neo4j_session,
                postgres_session=postgres_session,
            )
            bma_results.append(bma)
        return bma_results

    dag.add_node(
        "bma",
        bma_wrapper,
        depends_on=["scoring", "sde", "hmm"],
        timeout_seconds=60,
    )

    # ── Alert nodes (batch 3 — depend on scoring) ──────────
    from models.ensemble.kelly_prioritiser import update_alert_kelly_scores

    async def kelly_wrapper(**kwargs):
        bma_results = kwargs.get("bma_results") or []
        return await update_alert_kelly_scores(bma_results, postgres_session)

    dag.add_node(
        "kelly",
        kelly_wrapper,
        depends_on=["bma"],
        timeout_seconds=30,
    )

    from alerts.advisory_generator import AdvisoryGenerator

    async def advisory_wrapper(**kwargs):
        scoring_results = kwargs.get("scoring_results") or []
        bma_results = kwargs.get("bma_results") or []
        gen = AdvisoryGenerator()
        return await gen.generate_all_triggered(
            risk_scores=scoring_results,
            bma_results=bma_results,
            postgres_session=postgres_session,
            neo4j_session=neo4j_session,
        )

    dag.add_node(
        "advisory",
        advisory_wrapper,
        depends_on=["kelly"],
        timeout_seconds=120,
    )

    # ── Reconcile node (final) — heal graph relationships so newly
    # ingested/model-written nodes are connected to their Region and
    # related nodes. Runs after everything so the graph is always
    # correctly wired for the visualiser / causal queries.
    from graph.node_writers import reconcile_graph_relationships

    async def reconcile_wrapper(**kwargs):
        return await reconcile_graph_relationships()

    dag.add_node(
        "reconcile",
        reconcile_wrapper,
        depends_on=["advisory"],
        timeout_seconds=120,
    )

    logger.info(
        "Pipeline DAG built: %d nodes",
        len(dag.nodes),
    )
    return dag
