"""HazardGraph — Bayesian Model Averaging engine.

Weights computed from exp(-BrierScore) and stored in PostgreSQL.
On Day 3, SDE and scoring_SERVICE outputs are available; other model
slots default to equal weight and will be populated on Day 5.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from db.neo4j_client import neo4j_client
from db.postgres_client import async_session_factory
from risk.scoring_service import RegionRiskScore

logger = logging.getLogger(__name__)

MODEL_NAMES = [
    "SDE", "HMM", "VARLiNGAM", "LSTM",
    "XGBoost", "CNN", "TimeGPT", "PageRank",
]

DEFAULT_WEIGHTS = {
    "SDE": 0.20,
    "HMM": 0.15,
    "VARLiNGAM": 0.15,
    "LSTM": 0.15,
    "XGBoost": 0.15,
    "CNN": 0.05,
    "TimeGPT": 0.05,
    "PageRank": 0.10,
}


@dataclass
class BMAResult:
    region_id: str
    posterior_risk: float
    epistemic_uncertainty: float
    confidence: str
    model_weights: dict
    component_probabilities: dict


class BMAEngine:
    """Bayesian Model Averaging across all available model outputs."""

    MODEL_NAMES = MODEL_NAMES
    DEFAULT_WEIGHTS = DEFAULT_WEIGHTS

    async def load_weights(self, postgres_session) -> dict[str, float]:
        """Load weights from PostgreSQL model_performance table.

        Compute weight proportional to exp(-BrierScore) for available models.
        For models with no performance record: use DEFAULT_WEIGHTS.
        Normalise to sum = 1.0.
        """
        try:
            from sqlalchemy import text
            result = await postgres_session.execute(
                text(
                    "SELECT model_name, brier_score "
                    "FROM model_performance "
                    "WHERE brier_score IS NOT NULL"
                )
            )
            rows = result.fetchall()
        except Exception as exc:
            logger.warning("Failed to load model performance: %s", exc)
            rows = []

        available = {row[0]: row[1] for row in rows}
        weights: dict[str, float] = {}

        for model_name in self.MODEL_NAMES:
            if model_name in available:
                brier = available[model_name]
                weights[model_name] = np.exp(-brier)
            else:
                weights[model_name] = self.DEFAULT_WEIGHTS[model_name]

        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    async def compute_posterior(
        self,
        region_id: str,
        scoring_result: RegionRiskScore,
        sde_result: dict,
        hmm_posteriors: dict,
        neo4j_session,
        postgres_session,
    ) -> BMAResult:
        """Compute BMA posterior risk for a single region.

        Inputs (all normalised to 0-1 crisis probability):
          SDE:       max(sde_result p_drought_4w, p_flood_4w)
          HMM:       hmm_posteriors SevereDrought + FloodEmergency
          VARLiNGAM: scoring_result.components.rainfall (proxy)
          LSTM:      scoring_result.score / 100 (proxy until Day 5)
          XGBoost:   scoring_result.components.ipc (proxy until Day 5)
          CNN:       scoring_result.components.rainfall * 0.8 (proxy)
          TimeGPT:   scoring_result.score / 100 (proxy)
          PageRank:  scoring_result.components.network
        """
        weights = await self.load_weights(postgres_session)

        sde_prob = max(
            sde_result.get("p_drought_4w", 0.0),
            sde_result.get("p_flood_4w", 0.0),
        )

        hmm_prob = (
            hmm_posteriors.get("SevereDrought", 0.0)
            + hmm_posteriors.get("FloodEmergency", 0.0)
        )

        component_probabilities: dict[str, float] = {
            "SDE": sde_prob,
            "HMM": hmm_prob,
            "VARLiNGAM": scoring_result.components.get("rainfall", 0.0),
            "LSTM": scoring_result.score / 100.0,
            "XGBoost": scoring_result.components.get("ipc", 0.0),
            "CNN": scoring_result.components.get("rainfall", 0.0) * 0.8,
            "TimeGPT": scoring_result.score / 100.0,
            "PageRank": scoring_result.components.get("network", 0.0),
        }

        posterior = sum(
            component_probabilities[m] * weights.get(m, 0.0)
            for m in self.MODEL_NAMES
        )

        weighted_probs = [
            component_probabilities[m] * weights.get(m, 0.0)
            for m in self.MODEL_NAMES
        ]
        epistemic_uncertainty = float(np.std(weighted_probs))

        if epistemic_uncertainty < 0.08:
            confidence = "High"
        elif epistemic_uncertainty < 0.15:
            confidence = "Medium"
        else:
            confidence = "Low"

        now = datetime.now(timezone.utc).isoformat()
        bma_id = f"bma_{region_id}"

        weights_json = json.dumps(weights)

        await neo4j_client.execute_write(
            """MERGE (b:BMAScore {id: $id})
            SET b.posterior_risk = $posterior,
                b.epistemic_uncertainty = $uncertainty,
                b.model_weights_json = $weights_json,
                b.confidence = $confidence,
                b.computed_at = $now,
                b.region_id = $region_id""",
            {
                "id": bma_id,
                "posterior": posterior,
                "uncertainty": epistemic_uncertainty,
                "weights_json": weights_json,
                "confidence": confidence,
                "now": now,
                "region_id": region_id,
            },
        )

        return BMAResult(
            region_id=region_id,
            posterior_risk=round(posterior, 4),
            epistemic_uncertainty=round(epistemic_uncertainty, 4),
            confidence=confidence,
            model_weights=weights,
            component_probabilities={k: round(v, 4) for k, v in component_probabilities.items()},
        )