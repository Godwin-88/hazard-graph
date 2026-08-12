"""HazardGraph — On-demand pipeline & model execution API.

Allows officers to trigger the full ML pipeline DAG or a single model
from the UI (Model Runner), and to inspect recent job runs. Long-running
jobs are executed as background asyncio tasks so the HTTP request returns
immediately with a run_id that the UI can poll.
"""

import asyncio
import logging
import traceback
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from auth.jwt_service import require_officer
from db.postgres_client import async_session_factory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


# ── Registry of runnable model jobs (mirrors scheduler/jobs.py) ──
# name → (label, layer, scheduler function)
MODEL_REGISTRY = {
    "chirps": ("CHIRPS Rainfall Ingestion", "Ingestion", "_run_chirps_ingestion"),
    "wfp": ("WFP Food Price Ingestion", "Ingestion", "_run_wfp_ingestion"),
    "ipc": ("IPC Phase Ingestion", "Ingestion", "_run_ipc_ingestion"),
    "icpac": ("ICPAC RSS Feed Ingestion", "Ingestion", "_run_icpac_ingestion"),
    "sde": ("Rainfall SDE Simulation", "Stochastic", "_run_sde_simulation"),
    "hmm": ("HMM Climate Regime Update", "Stochastic", "_run_hmm_regime_update"),
    "varlingam": ("VARLiNGAM Causal Discovery", "Causal", "_run_varlingam_discovery"),
    "lstm": ("LSTM Drought Forecast", "ML", "_run_lstm_forecast"),
    "xgb": ("XGBoost Food Crisis Prediction", "ML", "_run_xgb_forecast"),
    "cnn_ndvi": ("CNN NDVI Anomaly Detection", "ML", "_run_cnn_ndvi"),
    "timegpt": ("TimeGPT Ensemble Forecast", "ML", "_run_timegpt_ensemble"),
    "pagerank": ("PageRank Vulnerability Update", "Network", "_run_pagerank_update"),
    "louvain": ("Louvain Community Detection", "Network", "_run_louvain_clusters"),
    "sir": ("SIR Contagion Cascade", "Network", "_run_sir_cascade"),
    "ppo": ("PPO Alert Policy Training", "RL", "_run_ppo_training"),
    "snapshot": ("Weekly Graph Snapshot", "Ops", "_run_graph_snapshot"),
    "scoring": ("Compound Risk Scoring (Full DAG)", "Ensemble", "_run_risk_scoring"),
}


class PipelineRunRequest(BaseModel):
    """Payload describing what to execute."""

    scope: str = "full"  # "full" | "scoring" | "models"
    models: list[str] | None = None  # list of model names from MODEL_REGISTRY


async def _log_job_start(job_name: str) -> str:
    """Insert a 'running' JobRun row, return its id."""
    run_id = str(uuid.uuid4())
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO job_runs "
                "(id, job_name, status, started_at, created_at) "
                "VALUES (:id, :name, 'running', NOW(), NOW())"
            ),
            {"id": run_id, "name": job_name},
        )
        await session.commit()
        return run_id


async def _log_job_finish(run_id: str, status: str, records: int = 0, error: str = None) -> None:
    """Finalise a JobRun row with status, duration and error."""
    async with async_session_factory() as session:
        await session.execute(
            text(
                "UPDATE job_runs SET "
                "status = :status, finished_at = NOW(), "
                "duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))::int, "
                "records_processed = :records, error_message = :error "
                "WHERE id = :id"
            ),
            {"status": status, "records": records, "error": error, "id": run_id},
        )
        await session.commit()


async def _log_job_error(
    run_id: str,
    job_name: str,
    exc: Exception,
    node_name: str | None = None,
) -> None:
    """Insert a structured error log row for a failed job run.

    Captures the error type, message, full traceback, and (for DAG runs)
    the specific node that failed. The UI renders this as a detailed,
    actionable error view.
    """
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO job_error_logs "
                "(id, run_id, job_name, error_type, error_message, traceback, node_name, created_at) "
                "VALUES (gen_random_uuid(), :run_id, :job_name, :etype, :emsg, :tb, :node, NOW())"
            ),
            {
                "run_id": run_id,
                "job_name": job_name,
                "etype": type(exc).__name__,
                "emsg": str(exc),
                "tb": tb,
                "node": node_name,
            },
        )
        await session.commit()


async def _run_model_in_background(run_id: str, job_name: str, func_name: str) -> None:
    """Execute a single model job as a background task, logging to JobRun."""
    try:
        from scheduler import jobs as scheduler_jobs

        func = getattr(scheduler_jobs, func_name, None)
        if func is None:
            raise RuntimeError(f"Unknown job function: {func_name}")
        await func()

        # Heal graph relationships after model runs so newly written
        # nodes are always connected (MEASURED_IN, IN_REGIME, CAUSES,
        # HAS_HAZARD, PREDICTS). Idempotent and safe to run repeatedly.
        try:
            from db.neo4j_client import neo4j_client
            from graph.node_writers import reconcile_graph_relationships
            await neo4j_client.connect()
            await reconcile_graph_relationships()
        except Exception as exc:
            logger.warning("Graph reconcile after %s failed: %s", job_name, exc)

        await _log_job_finish(run_id, "completed")
    except Exception as exc:
        logger.error("Model job %s failed: %s", job_name, exc)
        await _log_job_finish(run_id, "failed", error=str(exc))
        await _log_job_error(run_id, job_name, exc)


async def _run_full_dag_in_background(run_id: str, job_name: str, scope: str, models: list[str] | None) -> None:
    """Execute the full DAG (or selected scope) as a background task."""
    try:
        from db.neo4j_client import neo4j_client
        from db.redis_client import redis_client
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

        # Clear risk cache so the dashboard reflects fresh scores
        try:
            await redis_client.delete("risk:scores")
        except Exception:
            pass

        records = len(results.get("scoring", []))
        await _log_job_finish(run_id, "completed", records=records)
    except Exception as exc:
        logger.error("Pipeline run failed: %s", exc)
        await _log_job_finish(run_id, "failed", error=str(exc))
        await _log_job_error(run_id, job_name, exc)


@router.post("/run", dependencies=[Depends(require_officer)])
async def run_pipeline(req: PipelineRunRequest):
    """Trigger the ML pipeline DAG (or selected models) in the background."""
    if req.scope == "full":
        run_id = await _log_job_start("pipeline_full_dag")
        asyncio.create_task(_run_full_dag_in_background(run_id, "pipeline_full_dag", "full", req.models))
        return {"run_id": run_id, "status": "running", "scope": "full", "message": "Full pipeline DAG starting in background"}

    if req.scope == "scoring":
        run_id = await _log_job_start("pipeline_scoring")
        asyncio.create_task(_run_full_dag_in_background(run_id, "pipeline_scoring", "scoring", req.models))
        return {"run_id": run_id, "status": "running", "scope": "scoring", "message": "Risk scoring DAG starting in background"}

    if req.scope == "models":
        models = req.models or []
        if not models:
            raise HTTPException(status_code=400, detail="models list is required when scope='models'")
        invalid = [m for m in models if m not in MODEL_REGISTRY]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Unknown model(s): {invalid}")
        started = []
        for m in models:
            run_id = await _log_job_start(m)
            asyncio.create_task(
                _run_model_in_background(run_id, m, MODEL_REGISTRY[m][2])
            )
            started.append({"model": m, "run_id": run_id, "label": MODEL_REGISTRY[m][0]})
        return {"status": "started", "runs": started}

    raise HTTPException(status_code=400, detail="scope must be 'full', 'scoring', or 'models'")


@router.post("/models/{name}", dependencies=[Depends(require_officer)])
async def run_single_model(name: str):
    """Run a single model/job by registry name."""
    entry = MODEL_REGISTRY.get(name)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown model: {name}")
    run_id = await _log_job_start(name)
    asyncio.create_task(_run_model_in_background(run_id, name, entry[2]))
    return {"run_id": run_id, "status": "running", "model": name, "label": entry[0]}


@router.get("/jobs", dependencies=[Depends(require_officer)])
async def get_job_history(limit: int = 50):
    """Return recent JobRun records for the monitoring panel."""
    async with async_session_factory() as session:
        result = await session.execute(
            text(
                "SELECT id, job_name, status, started_at, finished_at, "
                "       duration_seconds, records_processed, error_message "
                "FROM job_runs ORDER BY started_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
        rows = result.fetchall()
    return {
        "jobs": [
            {
                "id": str(r[0]),
                "job_name": r[1],
                "status": r[2],
                "started_at": r[3].isoformat() if r[3] else None,
                "finished_at": r[4].isoformat() if r[4] else None,
                "duration_seconds": r[5],
                "records_processed": r[6],
                "error_message": r[7],
            }
            for r in rows
        ]
    }


@router.get("/jobs/{run_id}/errors", dependencies=[Depends(require_officer)])
async def get_job_errors(run_id: str):
    """Return structured error logs for a specific job run.

    Used by the UI to render a detailed error view (error type, message,
    full traceback, and the DAG node that failed) for a failed model run.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            text(
                "SELECT id, run_id, job_name, error_type, error_message, "
                "       traceback, node_name, created_at "
                "FROM job_error_logs WHERE run_id = :run_id "
                "ORDER BY created_at DESC",
            ),
            {"run_id": run_id},
        )
        rows = result.fetchall()
    return {
        "errors": [
            {
                "id": str(r[0]),
                "run_id": str(r[1]),
                "job_name": r[2],
                "error_type": r[3],
                "error_message": r[4],
                "traceback": r[5],
                "node_name": r[6],
                "created_at": r[7].isoformat() if r[7] else None,
            }
            for r in rows
        ]
    }


@router.get("/status", dependencies=[Depends(require_officer)])
async def get_pipeline_status():
    """Return the registry of runnable models + last run status for each."""
    async with async_session_factory() as session:
        result = await session.execute(
            text(
                "SELECT DISTINCT ON (job_name) job_name, status, finished_at, records_processed "
                "FROM job_runs ORDER BY job_name, started_at DESC"
            )
        )
        rows = result.fetchall()

    last_runs = {r[0]: {"status": r[1], "finished_at": r[2], "records": r[3]} for r in rows}

    models = []
    for name, (label, layer, _func) in MODEL_REGISTRY.items():
        last = last_runs.get(name)
        models.append({
            "name": name,
            "label": label,
            "layer": layer,
            "last_status": last["status"] if last else "never_run",
            "last_finished_at": last["finished_at"].isoformat() if last and last["finished_at"] else None,
            "last_records": last["records"] if last else None,
        })

    return {"models": models}