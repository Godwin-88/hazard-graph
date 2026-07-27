"""HazardGraph — Kelly alert prioritisation engine.

Adapted from GraphAlpha Formula f_kelly.
f* = (bp - q) / b
Here b=1 (binary), p=posterior_risk, q=1-p

Kelly Priority = p - (1 - p) = 2p - 1

Epistemic discount:
    effective_priority = kelly_score * (1 - epistemic_uncertainty)

Negative kelly_score -> do not send (insufficient evidence).
"""

import logging
from typing import List, Tuple

from models.ensemble.bma_engine import BMAResult

logger = logging.getLogger(__name__)


def compute_kelly_priority(bma_result: BMAResult) -> float:
    """Compute Kelly priority score in [-1, 1].

    Positive -> send alert, higher = more urgent.
    Negative -> withhold alert.

    Formula: kelly = (2 * p - 1) * (1 - epistemic_uncertainty)
    where p = posterior_risk.
    """
    p = bma_result.posterior_risk
    kelly = 2 * p - 1
    return kelly * (1 - bma_result.epistemic_uncertainty)


def rank_alerts(
    bma_results: List[BMAResult],
    min_kelly: float = 0.10,
) -> List[Tuple[BMAResult, float]]:
    """Return list of (BMAResult, kelly_score) sorted descending.

    Filters out results with kelly_score < min_kelly.
    """
    scored = []
    for result in bma_results:
        score = compute_kelly_priority(result)
        if score >= min_kelly:
            scored.append((result, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


async def update_alert_kelly_scores(
    bma_results: List[BMAResult],
    postgres_session,
) -> None:
    """Update kelly_priority field on all pending Alert rows in PostgreSQL.

    For each BMA result, sets kelly_priority on pending alerts for the
    corresponding region.
    """
    from sqlalchemy import text

    for result in bma_results:
        score = compute_kelly_priority(result)
        try:
            await postgres_session.execute(
                text(
                    "UPDATE alerts SET kelly_priority = :score "
                    "WHERE region_id = :region_id AND status = 'pending'"
                ),
                {"score": score, "region_id": result.region_id},
            )
        except Exception as exc:
            logger.warning(
                "Failed to update kelly_priority for region %s: %s",
                result.region_id, exc,
            )
        else:
            logger.info(
                "Updated kelly_priority=%.4f for region %s (%d pending alerts)",
                score, result.region_id,
            )