"""HazardGraph — Agent tool: check model health (Brier score + BMA weight).

Reads from the model_performance PostgreSQL table to assess whether
any model is underperforming (Brier score > 0.25) and needs retraining.
"""

import logging

logger = logging.getLogger(__name__)

BRIER_THRESHOLD = 0.25


async def check_model_health(model_ids: list[str]) -> dict:
    """Check health for the given model IDs.

    Reads brier_score, bma_weight, and trained_at from the
    model_performance table. Flags any model with Brier score > 0.25
    as needing retraining.

    Args:
        model_ids: List of model IDs (e.g. ["M1", "M2", ...]).

    Returns:
        dict mapping model ID → health status dict.
    """
    result = {}

    try:
        from db.postgres_client import async_session_factory
        from sqlalchemy import text

        async with async_session_factory() as session:
            rows_result = await session.execute(
                text(
                    "SELECT model_id, model_name, brier_score, bma_weight, "
                    "       trained_at, status "
                    "FROM model_performance "
                    "WHERE model_id = ANY(:ids)"
                ),
                {"ids": model_ids},
            )
            rows = rows_result.fetchall()
    except Exception as exc:
        logger.warning("Model health check failed: %s", exc)
        rows = []

    # Build lookup by model_id
    by_id = {}
    for row in rows:
        by_id[row[0]] = {
            "model_name": row[1],
            "brier_score": float(row[2]) if row[2] is not None else None,
            "bma_weight": float(row[3]) if row[3] is not None else None,
            "trained_at": str(row[4]) if row[4] is not None else None,
            "status": row[5] or "active",
        }

    for model_id in model_ids:
        rec = by_id.get(model_id)
        if rec is None:
            result[model_id] = {
                "brier_score": None,
                "bma_weight": None,
                "status": "unknown",
                "needs_retraining": False,
                "note": "No performance record found in model_performance table",
            }
            continue

        brier = rec["brier_score"]
        needs_retraining = brier is not None and brier > BRIER_THRESHOLD

        result[model_id] = {
            "model_name": rec["model_name"],
            "brier_score": brier,
            "bma_weight": rec["bma_weight"],
            "trained_at": rec["trained_at"],
            "status": "needs_retraining" if needs_retraining else rec["status"],
            "needs_retraining": needs_retraining,
            "brier_threshold": BRIER_THRESHOLD,
        }

    return result