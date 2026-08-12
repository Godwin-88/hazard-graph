"""HazardGraph — All APScheduler job registrations.

Uses AsyncIOScheduler integrated into the FastAPI lifespan.
Each job logs its run to the PostgreSQL job_runs table.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db.postgres_client import async_session_factory
from models.postgres.jobs import JobRun

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _log_job_run(
    job_name: str,
    status: str,
    records_processed: int = 0,
    error_message: str = None,
) -> None:
    """Persist a job run record to PostgreSQL."""
    try:
        async with async_session_factory() as session:
            run = JobRun(
                job_name=job_name,
                status=status,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                records_processed=records_processed,
                error_message=error_message,
            )
            session.add(run)
            await session.commit()
    except Exception as exc:
        logger.error("Failed to log job run for %s: %s", job_name, exc)


async def _run_icpac_ingestion() -> None:
    """Wrapper for ICPAC RSS ingestion."""
    job_name = "icpac_rss_fetch"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from ingestion.icpac_rss_fetcher import ingest_icpac_rss
        summary = await ingest_icpac_rss()
        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=summary.get("processed", 0),
        )
        logger.info("Scheduled job %s completed: %s", job_name, summary)
    except Exception as exc:
        logger.error("Scheduled job %s failed: %s", job_name, exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_varlingam_discovery() -> None:
    """Monthly VARLiNGAM causal discovery for all regions."""
    job_name = "varlingam_discovery"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from causal.time_series_assembler import assemble_panel
        from causal.varlingam_engine import VARLiNGAMEngine
        from causal.edge_writer import write_causal_edges

        regions = await neo4j_client.execute_read(
            "MATCH (r:Region) RETURN r.id AS id"
        )
        engine = VARLiNGAMEngine()
        total_edges = 0

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
                logger.error("VARLiNGAM failed for region %s: %s", region_id, exc)
                continue

        # Heal graph relationships (connect newly discovered CausalEdges)
        try:
            from graph.node_writers import reconcile_graph_relationships
            await reconcile_graph_relationships()
        except Exception as exc:
            logger.warning("Graph reconcile after %s failed: %s", job_name, exc)

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=total_edges,
        )
        logger.info("VARLiNGAM discovery complete: %d total edges", total_edges)

    except Exception as exc:
        logger.error("VARLiNGAM discovery job failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_hmm_regime_update() -> None:
    """Weekly HMM regime update for all regions."""
    job_name = "hmm_regime_update"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from regime.regime_updater import update_all_regimes
        summary = await update_all_regimes()

        # Heal graph relationships (create IN_REGIME edges from updated regimes)
        try:
            from graph.node_writers import reconcile_graph_relationships
            await reconcile_graph_relationships()
        except Exception as exc:
            logger.warning("Graph reconcile after %s failed: %s", job_name, exc)

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=summary.get("updated", 0),
        )
        logger.info("HMM regime update complete: %s", summary)
    except Exception as exc:
        logger.error("HMM regime update failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_chirps_ingestion() -> None:
    """Daily CHIRPS rainfall ingestion."""
    job_name = "chirps_ingestion"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from ingestion.chirps_fetcher import fetch_all_regions
        summary = await fetch_all_regions()
        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=summary.get("success", 0),
        )
        logger.info("CHIRPS ingestion complete: %s", summary)
    except Exception as exc:
        logger.error("CHIRPS ingestion failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_wfp_ingestion() -> None:
    """Weekly WFP food price ingestion."""
    job_name = "wfp_ingestion"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from ingestion.wfp_fetcher import fetch_all_countries
        summary = await fetch_all_countries()
        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=summary.get("total_signals", 0),
        )
        logger.info("WFP ingestion complete: %s", summary)
    except Exception as exc:
        logger.error("WFP ingestion failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_ipc_ingestion() -> None:
    """Weekly IPC phase ingestion."""
    job_name = "ipc_ingestion"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from ingestion.ipc_fetcher import fetch_all_countries
        summary = await fetch_all_countries()
        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=summary.get("signals_written", 0),
        )
        logger.info("IPC ingestion complete: %s", summary)
    except Exception as exc:
        logger.error("IPC ingestion failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_nasa_power_ingestion() -> None:
    """Daily NASA POWER climate ingestion."""
    job_name = "nasa_power_ingestion"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from ingestion.nasa_power_fetcher import fetch_all_regions
        summary = await fetch_all_regions()
        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=summary.get("success", 0),
        )
        logger.info("NASA POWER ingestion complete: %s", summary)
    except Exception as exc:
        logger.error("NASA POWER ingestion failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_faostat_ingestion() -> None:
    """Weekly FAOSTAT food price ingestion."""
    job_name = "faostat_ingestion"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from ingestion.faostat_fetcher import fetch_all_countries
        summary = await fetch_all_countries()
        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=summary.get("total_signals", 0),
        )
        logger.info("FAOSTAT ingestion complete: %s", summary)
    except Exception as exc:
        logger.error("FAOSTAT ingestion failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_ndvi_ingestion() -> None:
    """Weekly NDVI greenness ingestion."""
    job_name = "ndvi_ingestion"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from ingestion.ndvi_fetcher import fetch_all_regions
        summary = await fetch_all_regions()
        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=summary.get("success", 0),
        )
        logger.info("NDVI ingestion complete: %s", summary)
    except Exception as exc:
        logger.error("NDVI ingestion failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_acled_ingestion() -> None:
    """Weekly ACLED conflict ingestion."""
    job_name = "acled_ingestion"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from ingestion.acled_fetcher import fetch_conflict_data
        summary = await fetch_conflict_data()
        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=summary.get("success", 0),
        )
        logger.info("ACLED ingestion complete: %s", summary)
    except Exception as exc:
        logger.error("ACLED ingestion failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_sde_simulation() -> None:
    """Weekly SDE rainfall simulation for all regions."""
    job_name = "sde_simulation"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from models.stochastic.rainfall_sde import RainfallSDE

        engine = RainfallSDE()
        results = await engine.run_all_regions(neo4j_client)
        records = len(results)

        # Heal graph relationships (link new StochasticSignal -> Region etc.)
        try:
            from graph.node_writers import reconcile_graph_relationships
            await reconcile_graph_relationships()
        except Exception as exc:
            logger.warning("Graph reconcile after %s failed: %s", job_name, exc)

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=records,
        )
        logger.info("SDE simulation complete: %d regions", records)
    except Exception as exc:
        logger.error("SDE simulation failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_risk_scoring() -> None:
    """Weekly compound risk scoring pipeline using explicit DAG executor."""
    job_name = "risk_scoring"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from db.redis_client import redis_client
        from db.postgres_client import async_session_factory
        from pipeline.hazard_pipeline import build_pipeline

        async with async_session_factory() as postgres_session:
            dag = await build_pipeline(
                neo4j_session=neo4j_client,
                postgres_session=postgres_session,
                redis_client=redis_client,
            )
            results = await dag.execute(
                neo4j_session=neo4j_client,
                postgres_session=postgres_session,
                redis_client=redis_client,
            )

        await redis_client.set("risk:scores", "", ttl=0)

        records = len(results.get("scoring", []))
        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=records,
        )
        logger.info("Risk scoring DAG complete: %d regions, %d nodes executed", records, len(results))
    except Exception as exc:
        logger.error("Risk scoring failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


def register_jobs() -> None:
    """Register all scheduled jobs on the global scheduler."""
    # ICPAC RSS fetch: daily at 06:00 EAT (03:00 UTC)
    scheduler.add_job(
        _run_icpac_ingestion,
        trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
        id="icpac_rss_fetch",
        name="ICPAC RSS Feed Ingestion",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # VARLiNGAM causal discovery: monthly, 1st at 02:00 EAT (previous day 23:00 UTC)
    scheduler.add_job(
        _run_varlingam_discovery,
        trigger=CronTrigger(day=1, hour=23, minute=0, timezone="UTC"),
        id="varlingam_discovery",
        name="VARLiNGAM Causal Discovery",
        replace_existing=True,
        misfire_grace_time=7200,
        max_instances=1,
    )

    # HMM regime update: weekly Monday 07:30 EAT (04:30 UTC)
    scheduler.add_job(
        _run_hmm_regime_update,
        trigger=CronTrigger(day_of_week="mon", hour=4, minute=30, timezone="UTC"),
        id="hmm_regime_update",
        name="HMM Climate Regime Update",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # CHIRPS ingestion: daily at 07:00 EAT (04:00 UTC)
    scheduler.add_job(
        _run_chirps_ingestion,
        trigger=CronTrigger(hour=4, minute=0, timezone="UTC"),
        id="chirps_ingestion",
        name="CHIRPS Rainfall Ingestion",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # WFP food prices: weekly Monday 08:00 EAT (05:00 UTC)
    scheduler.add_job(
        _run_wfp_ingestion,
        trigger=CronTrigger(day_of_week="mon", hour=5, minute=0, timezone="UTC"),
        id="wfp_ingestion",
        name="WFP Food Price Ingestion",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # IPC phases: weekly Monday 08:30 EAT (05:30 UTC)
    scheduler.add_job(
        _run_ipc_ingestion,
        trigger=CronTrigger(day_of_week="mon", hour=5, minute=30, timezone="UTC"),
        id="ipc_ingestion",
        name="IPC Phase Ingestion",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # NASA POWER climate: daily at 07:15 EAT (04:15 UTC)
    scheduler.add_job(
        _run_nasa_power_ingestion,
        trigger=CronTrigger(hour=4, minute=15, timezone="UTC"),
        id="nasa_power_ingestion",
        name="NASA POWER Climate Ingestion",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # FAOSTAT food prices: weekly Monday 08:15 EAT (05:15 UTC)
    scheduler.add_job(
        _run_faostat_ingestion,
        trigger=CronTrigger(day_of_week="mon", hour=5, minute=15, timezone="UTC"),
        id="faostat_ingestion",
        name="FAOSTAT Food Price Ingestion",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # NDVI greenness: weekly Monday 08:45 EAT (05:45 UTC)
    scheduler.add_job(
        _run_ndvi_ingestion,
        trigger=CronTrigger(day_of_week="mon", hour=5, minute=45, timezone="UTC"),
        id="ndvi_ingestion",
        name="NDVI Greenness Ingestion",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # ACLED conflict: weekly Monday 09:15 EAT (06:15 UTC)
    scheduler.add_job(
        _run_acled_ingestion,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=15, timezone="UTC"),
        id="acled_ingestion",
        name="ACLED Conflict Ingestion",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # SDE rainfall simulation: weekly Monday 07:45 EAT (04:45 UTC)
    scheduler.add_job(
        _run_sde_simulation,
        trigger=CronTrigger(day_of_week="mon", hour=4, minute=45, timezone="UTC"),
        id="sde_simulation",
        name="Rainfall SDE Simulation",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # Risk scoring pipeline: weekly Monday 09:00 EAT (06:00 UTC)
    scheduler.add_job(
        _run_risk_scoring,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=0, timezone="UTC"),
        id="risk_scoring",
        name="Compound Risk Scoring",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # LSTM forecast: weekly Monday 09:30 EAT (06:30 UTC)
    scheduler.add_job(
        _run_lstm_forecast,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=30, timezone="UTC"),
        id="lstm_forecast",
        name="LSTM Drought Forecast",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # XGBoost forecast: weekly Monday 09:45 EAT (06:45 UTC)
    scheduler.add_job(
        _run_xgb_forecast,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=45, timezone="UTC"),
        id="xgb_forecast",
        name="XGBoost Food Crisis Prediction",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # PageRank update: weekly Monday 10:00 EAT (07:00 UTC)
    scheduler.add_job(
        _run_pagerank_update,
        trigger=CronTrigger(day_of_week="mon", hour=7, minute=0, timezone="UTC"),
        id="pagerank_update",
        name="PageRank Vulnerability Update",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # CNN NDVI inference: weekly Monday 09:50 EAT (06:50 UTC)
    scheduler.add_job(
        _run_cnn_ndvi,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=50, timezone="UTC"),
        id="cnn_ndvi",
        name="CNN NDVI Anomaly Detection",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # TimeGPT ensemble: weekly Monday 10:05 EAT (07:05 UTC)
    scheduler.add_job(
        _run_timegpt_ensemble,
        trigger=CronTrigger(day_of_week="mon", hour=7, minute=5, timezone="UTC"),
        id="timegpt_ensemble",
        name="TimeGPT Ensemble Forecast",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # Louvain clusters: monthly 1st Monday 03:00 EAT (00:00 UTC)
    scheduler.add_job(
        _run_louvain_clusters,
        trigger=CronTrigger(day=1, hour=0, minute=0, timezone="UTC"),
        id="louvain_clusters",
        name="Louvain Community Detection",
        replace_existing=True,
        misfire_grace_time=7200,
        max_instances=1,
    )

    # SIR cascade: weekly Monday 10:20 EAT (07:20 UTC)
    scheduler.add_job(
        _run_sir_cascade,
        trigger=CronTrigger(day_of_week="mon", hour=7, minute=20, timezone="UTC"),
        id="sir_cascade",
        name="SIR Contagion Cascade",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # PPO policy training: monthly 1st Monday 04:00 EAT (01:00 UTC)
    scheduler.add_job(
        _run_ppo_training,
        trigger=CronTrigger(day=1, hour=1, minute=0, timezone="UTC"),
        id="ppo_training",
        name="PPO Alert Policy Training",
        replace_existing=True,
        misfire_grace_time=7200,
        max_instances=1,
    )

    # Graph snapshot: weekly Sunday 23:00 EAT (20:00 UTC)
    scheduler.add_job(
        _run_graph_snapshot,
        trigger=CronTrigger(day_of_week="sun", hour=20, minute=0, timezone="UTC"),
        id="graph_snapshot",
        name="Weekly Graph Snapshot",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # DataHub metadata sync: weekly Monday 08:00 EAT (05:00 UTC)
    scheduler.add_job(
        _run_datahub_sync,
        trigger=CronTrigger(day_of_week="mon", hour=5, minute=0, timezone="UTC"),
        id="datahub_sync",
        name="DataHub Metadata Sync",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    logger.info("Registered %d scheduled jobs", len(scheduler.get_jobs()))


async def _run_lstm_forecast() -> None:
    """Weekly LSTM drought forecast for all regions."""
    job_name = "lstm_forecast"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from models.ml.lstm_drought import LSTMDroughtForecaster
        from models.ml.feature_pipeline import FeaturePipeline

        assembler = FeaturePipeline()
        forecaster = LSTMDroughtForecaster()
        async with neo4j_client.session() as session:
            results = await forecaster.run_all_regions(assembler, session)

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=len(results),
        )
        logger.info("LSTM forecast complete: %d regions", len(results))
    except Exception as exc:
        logger.error("LSTM forecast failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_xgb_forecast() -> None:
    """Weekly XGBoost food crisis prediction for all regions."""
    job_name = "xgb_forecast"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from models.ml.xgb_food_crisis import XGBFoodCrisisPredictor

        predictor = XGBFoodCrisisPredictor()
        async with neo4j_client.session() as session:
            results = await predictor.run_all_regions(session)

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=len(results),
        )
        logger.info("XGBoost forecast complete: %d regions", len(results))
    except Exception as exc:
        logger.error("XGBoost forecast failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_pagerank_update() -> None:
    """Weekly PageRank vulnerability update for all regions."""
    job_name = "pagerank_update"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from risk.scoring_service import get_latest_risk_scores
        from risk.vulnerability_data import get_all_vulnerability_multipliers
        from models.network.pagerank_vulnerability import RegionalVulnerabilityNetwork

        # Get current risk scores
        async with neo4j_client.session() as session:
            risk_scores = await get_latest_risk_scores(session)

        vulnerability_multipliers = get_all_vulnerability_multipliers()

        network = RegionalVulnerabilityNetwork()
        results = network.compute_pagerank(risk_scores, vulnerability_multipliers)

        async with neo4j_client.session() as session:
            await network.update_neo4j(results, session)

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=len(results),
        )
        logger.info("PageRank update complete: %d regions", len(results))
    except Exception as exc:
        logger.error("PageRank update failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_cnn_ndvi() -> None:
    """Weekly CNN NDVI anomaly detection for all regions."""
    job_name = "cnn_ndvi"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from models.ml.ndvi_cnn import NDVIAnomalyDetector

        detector = NDVIAnomalyDetector()
        async with neo4j_client.session() as session:
            results = await detector.run_all_regions(session)

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=len(results),
        )
        logger.info("CNN NDVI complete: %d regions", len(results))
    except Exception as exc:
        logger.error("CNN NDVI failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_timegpt_ensemble() -> None:
    """Weekly TimeGPT ensemble forecast for all regions."""
    job_name = "timegpt_ensemble"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from models.ml.timeseries_ensemble import TimeSeriesEnsemble
        from models.ml.feature_pipeline import FeaturePipeline

        assembler = FeaturePipeline()
        ensemble = TimeSeriesEnsemble()
        async with neo4j_client.session() as session:
            results = await ensemble.run_all_regions(assembler, session)

        total = sum(len(v) for v in results.values())
        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=total,
        )
        logger.info("TimeGPT ensemble complete: %d forecasts", total)
    except Exception as exc:
        logger.error("TimeGPT ensemble failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_louvain_clusters() -> None:
    """Monthly Louvain community detection."""
    job_name = "louvain_clusters"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from risk.scoring_service import get_latest_risk_scores
        from models.network.community_detection import LouvainHazardClustering
        from config.settings import settings
        from groq import AsyncGroq

        async with neo4j_client.session() as session:
            risk_scores = await get_latest_risk_scores(session)
            risk_dict = {r.id: r.score for r in risk_scores}
            regimes = {r.id: r.current_regime for r in risk_scores}
            spi_values = {r.id: 0.0 for r in risk_scores}

            result = await neo4j_client.execute_read(
                'MATCH (e:CausalEdge {active: true}) '
                'RETURN e.region_id as r, e.source_variable as s, '
                '       e.target_variable as t, e.weight as w'
            )
            causal_density = {}
            for rec in result:
                causal_density[(rec['r'], rec['t'])] = float(rec['w'])

            groq_client = AsyncGroq(api_key=settings.groq_api_key)
            clustering = LouvainHazardClustering()
            clusters = await clustering.run(
                risk_dict, regimes, spi_values,
                causal_density, session, groq_client
            )

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=len(clusters),
        )
        logger.info("Louvain clusters complete: %d clusters", len(clusters))
    except Exception as exc:
        logger.error("Louvain clusters failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_sir_cascade() -> None:
    """Weekly SIR cascade for top-3 risk regions."""
    job_name = "sir_cascade"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from risk.scoring_service import get_latest_risk_scores
        from risk.vulnerability_data import get_all_vulnerability_multipliers
        from models.network.contagion_cascade import SIRCascadeSimulator

        async with neo4j_client.session() as session:
            risk_scores = await get_latest_risk_scores(session)
            risk_dict = {r.id: r.score for r in risk_scores}
            vuln = get_all_vulnerability_multipliers()

            sim = SIRCascadeSimulator()
            results = await sim.run_top3(risk_dict, vuln, session)

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=len(results),
        )
        logger.info("SIR cascade complete: %d simulations", len(results))
    except Exception as exc:
        logger.error("SIR cascade failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_ppo_training() -> None:
    """Monthly PPO policy retraining on accumulated snapshot history."""
    job_name = "ppo_training"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from models.rl.ppo_trainer import PPOTrainer

        trainer = PPOTrainer()
        trainer.train(n_iterations=100, verbose=False)

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=1,
        )
        logger.info("PPO training complete")
    except Exception as exc:
        logger.error("PPO training failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_datahub_sync() -> None:
    """Weekly DataHub metadata sync — datasets, models, lineage, assertions."""
    job_name = "datahub_sync"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from hazarddatahub.sync_job import sync_all

        summary = sync_all()
        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=summary.get("models", 0),
        )
        logger.info("DataHub sync complete: %s", summary)
    except Exception as exc:
        logger.error("DataHub sync failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


async def _run_graph_snapshot() -> None:
    """Weekly graph snapshot for temporal DRL training."""
    job_name = "graph_snapshot"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from graph.temporal_snapshots import save_weekly_snapshot

        async with neo4j_client.session() as session:
            snapshot_id = await save_weekly_snapshot(session)

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=1,
        )
        logger.info("Graph snapshot complete: %s", snapshot_id)
    except Exception as exc:
        logger.error("Graph snapshot failed: %s", exc)
        await _log_job_run(job_name=job_name, status="failed", error_message=str(exc))


def start_scheduler() -> None:
    """Start the APScheduler."""
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started")


def stop_scheduler() -> None:
    """Shut down the APScheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")