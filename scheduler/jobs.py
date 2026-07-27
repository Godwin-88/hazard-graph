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
    """Weekly compound risk scoring pipeline."""
    job_name = "risk_scoring"
    logger.info("Starting scheduled job: %s", job_name)
    try:
        from db.neo4j_client import neo4j_client
        from risk.scoring_service import compute_risk_scores
        from models.ensemble.bma_engine import BMAEngine
        from models.stochastic.rainfall_sde import RainfallSDE
        from models.ensemble.kelly_prioritiser import update_alert_kelly_scores
        from db.redis_client import redis_client
        from db.postgres_client import async_session_factory

        scoring_results = await compute_risk_scores(neo4j_client)
        sde_results = await RainfallSDE().run_all_regions(neo4j_client)

        bma_results_local = []
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
                bma_result = await BMAEngine().compute_posterior(
                    region_id=score_result.region_id,
                    scoring_result=score_result,
                    sde_result=sde_data,
                    hmm_posteriors=hmm_posteriors,
                    neo4j_session=neo4j_client,
                    postgres_session=postgres_session,
                )
                bma_results_local.append(bma_result)

        async with async_session_factory() as kelly_session:
            await update_alert_kelly_scores(bma_results_local, kelly_session)
        await redis_client.set("risk:scores", "", ttl=0)

        await _log_job_run(
            job_name=job_name,
            status="completed",
            records_processed=len(scoring_results),
        )
        logger.info("Risk scoring complete: %d regions", len(scoring_results))
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

    logger.info("Registered %d scheduled jobs", len(scheduler.get_jobs()))


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