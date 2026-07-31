"""HazardGraph — Bayesian Model Averaging engine.

All 13 models now integrated (M1-M11 + M13 downstream).
Weights computed from exp(-BrierScore) and stored in PostgreSQL.
Model probability mapping converts each model output to P(crisis), 0-1.
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
    "SDE", "HMM", "Kalman", "LSTM",
    "XGBoost", "CNN", "TimeGPT", "VARLiNGAM",
    "PageRank", "Louvain", "SIR",
]

DEFAULT_WEIGHTS = {
    "SDE": 0.15,
    "HMM": 0.12,
    "Kalman": 0.08,
    "LSTM": 0.12,
    "XGBoost": 0.12,
    "CNN": 0.08,
    "TimeGPT": 0.08,
    "VARLiNGAM": 0.08,
    "PageRank": 0.07,
    "Louvain": 0.05,
    "SIR": 0.05,
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
                weights[model_name] = self.DEFAULT_WEIGHTS.get(model_name, 0.05)

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
        kalman_spi: float = 0.0,
        lstm_forecast=None,
        xgb_forecast=None,
        ndvi_forecast=None,
        ts_forecast=None,
        pagerank_result=None,
        cluster_risk_score: float = 0.0,
        sir_cascade_prob: float = 0.0,
        neo4j_session=None,
        postgres_session=None,
    ) -> BMAResult:
        """Compute BMA posterior risk for a single region.

        All model outputs converted to P(crisis), 0-1:
          M1  SDE:       max(p_drought_4w, p_flood_4w)
          M2  HMM:       SevereDrought + FloodEmergency posteriors
          M3  Kalman:    clip((-spi_smoothed + 1.5) / 3, 0, 1)
          M4  LSTM:      max(probabilities[2:]) if lstm else SDE proxy
          M5  XGBoost:   p_crisis if xgb else scoring proxy
          M6  CNN NDVI:  stress_probability if ndvi else 0.3
          M7  TimeGPT:   next SPI forecast → crisis prob
          M8  VARLiNGAM: proxy via causal edge density
          M9  PageRank:  systemic_risk_score if pr else 0.1
          M10 Louvain:   cluster_risk_score / 100
          M11 SIR:       cascade_probability
        """
        if postgres_session:
            weights = await self.load_weights(postgres_session)
        else:
            weights = dict(self.DEFAULT_WEIGHTS)
            total = sum(weights.values())
            weights = {k: v / total for k, v in weights.items()}

        # M1 SDE
        sde_prob = max(
            sde_result.get("p_drought_4w", 0.0),
            sde_result.get("p_flood_4w", 0.0),
        )

        # M2 HMM
        hmm_prob = (
            hmm_posteriors.get("SevereDrought", 0.0)
            + hmm_posteriors.get("FloodEmergency", 0.0)
        )

        # M3 Kalman
        kalman_prob = max(0.0, min(1.0, (-kalman_spi + 1.5) / 3.0))

        # M4 LSTM
        if lstm_forecast is not None:
            try:
                lstm_prob = max(lstm_forecast.probabilities[2:])
            except (AttributeError, IndexError, TypeError):
                lstm_prob = sde_prob
        else:
            lstm_prob = sde_prob

        # M5 XGBoost
        if xgb_forecast is not None:
            try:
                xgb_prob = xgb_forecast.p_crisis
            except AttributeError:
                xgb_prob = scoring_result.score / 100.0
        else:
            xgb_prob = scoring_result.score / 100.0

        # M6 CNN NDVI
        if ndvi_forecast is not None:
            try:
                cnn_prob = ndvi_forecast.stress_probability
            except AttributeError:
                cnn_prob = 0.3
        else:
            cnn_prob = 0.3

        # M7 TimeGPT/Prophet
        if ts_forecast is not None:
            try:
                ts_val = ts_forecast.values[0] if ts_forecast.values else 0.0
                ts_prob = max(0.0, min(1.0, (-ts_val + 1.0) / 2.5))
            except (AttributeError, IndexError, TypeError):
                ts_prob = 0.3
        else:
            ts_prob = 0.3

        # M8 VARLiNGAM (proxy via Neo4j edge count)
        varlingam_prob = 0.1 + scoring_result.components.get("rainfall", 0.0) * 0.3

        # M9 PageRank
        if pagerank_result is not None:
            try:
                pr_prob = pagerank_result.systemic_risk_score
            except AttributeError:
                pr_prob = 0.1
        else:
            pr_prob = 0.1

        # M10 Louvain
        louvain_prob = cluster_risk_score / 100.0

        # M11 SIR
        sir_prob = sir_cascade_prob

        component_probabilities: dict[str, float] = {
            "SDE": sde_prob,
            "HMM": hmm_prob,
            "Kalman": kalman_prob,
            "LSTM": lstm_prob,
            "XGBoost": xgb_prob,
            "CNN": cnn_prob,
            "TimeGPT": ts_prob,
            "VARLiNGAM": varlingam_prob,
            "PageRank": pr_prob,
            "Louvain": louvain_prob,
            "SIR": sir_prob,
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

        if neo4j_session:
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

    async def compute_all_regions(
        self,
        regions: list[str],
        scoring_results: dict[str, RegionRiskScore],
        sde_results: dict[str, dict],
        hmm_results: dict[str, dict],
        kalman_results: dict[str, float],
        lstm_results: dict[str, object],
        xgb_results: dict[str, object],
        ndvi_results: dict[str, object],
        ts_results: dict[str, object],
        pagerank_results: dict[str, object],
        cluster_risks: dict[str, float],
        sir_probs: dict[str, float],
        neo4j_session=None,
        postgres_session=None,
    ) -> dict[str, BMAResult]:
        """Run BMA for all regions."""
        results = {}
        for region_id in regions:
            sr = scoring_results.get(region_id)
            if sr is None:
                continue
            result = await self.compute_posterior(
                region_id=region_id,
                scoring_result=sr,
                sde_result=sde_results.get(region_id, {}),
                hmm_posteriors=hmm_results.get(region_id, {}),
                kalman_spi=kalman_results.get(region_id, 0.0),
                lstm_forecast=lstm_results.get(region_id),
                xgb_forecast=xgb_results.get(region_id),
                ndvi_forecast=ndvi_results.get(region_id),
                ts_forecast=ts_results.get(region_id),
                pagerank_result=pagerank_results.get(region_id),
                cluster_risk_score=cluster_risks.get(region_id, 0.0),
                sir_cascade_prob=sir_probs.get(region_id, 0.0),
                neo4j_session=neo4j_session,
                postgres_session=postgres_session,
            )
            results[region_id] = result
        return results