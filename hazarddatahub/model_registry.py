"""HazardGraph — Registers all 14 quantitative models as DataHub MLModel entities.

Called at startup and after each weekly training run.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from hazarddatahub.entities import MODELS

logger = logging.getLogger(__name__)


@dataclass
class ModelSpec:
    id: str
    name: str
    urn_name: str
    category: str
    technique: str
    output_description: str
    update_frequency: str
    brier_score: Optional[float] = None
    bma_weight: Optional[float] = None
    upstream_datasets: Optional[list[str]] = None


# Complete model registry — all 14 models
MODEL_REGISTRY: list[ModelSpec] = [
    ModelSpec(
        id="M1",
        name="CIR + Jump Diffusion SDE",
        urn_name="cir_jump_diffusion_rainfall",
        category="Stochastic",
        technique="Mean-reverting jump-diffusion (Cox-Ingersoll-Ross + Poisson jumps)",
        output_description="P(flood/drought within 4 weeks) per IGAD sub-region",
        update_frequency="Weekly (Monday 06:35 UTC)",
        upstream_datasets=["chirps_spi_horn_of_africa"],
    ),
    ModelSpec(
        id="M2",
        name="Hidden Markov Model — Climate Regime Detector",
        urn_name="hidden_markov_regime_detector",
        category="Statistical",
        technique="5-state Gaussian HMM (Baum-Welch, Viterbi decoding)",
        output_description="HazardRegime label: {Dry, Normal, Wet, ExtremeDry, ExtremeWet}",
        update_frequency="Weekly (Monday 06:40 UTC)",
        upstream_datasets=["chirps_spi_horn_of_africa", "modis_ndvi_horn_of_africa",
                           "wfp_food_prices_igad"],
    ),
    ModelSpec(
        id="M3",
        name="Kalman Filter — SPI/NDVI Smoother",
        urn_name="kalman_filter_spi_smoother",
        category="Filtering",
        technique="Linear state-space Kalman filter (observation noise calibrated to sensor variance)",
        output_description="Smoothed SPI and NDVI signals with uncertainty bounds",
        update_frequency="Daily",
        upstream_datasets=["chirps_spi_horn_of_africa", "modis_ndvi_horn_of_africa"],
    ),
    ModelSpec(
        id="M4",
        name="Bidirectional LSTM — Drought Forecaster",
        urn_name="bilstm_drought_forecaster",
        category="Deep Learning",
        technique="2-layer BiLSTM ensemble (3 seeds, mean ensemble prediction)",
        output_description="P(IPC phase 1-5) at 4-week horizon per region",
        update_frequency="Weekly (Monday 06:45 UTC)",
        upstream_datasets=["chirps_spi_horn_of_africa", "modis_ndvi_horn_of_africa",
                           "ipc_phase_reports"],
    ),
    ModelSpec(
        id="M5",
        name="XGBoost + SHAP — Food Crisis Predictor",
        urn_name="xgb_food_crisis_predictor",
        category="ML — Gradient Boosting",
        technique="XGBoost with Platt scaling calibration + SHAP feature attribution",
        output_description="P(Crisis at IPC 3+) at 8-week horizon + SHAP explanation per region",
        update_frequency="Weekly (Monday 06:45 UTC)",
        upstream_datasets=["chirps_spi_horn_of_africa", "modis_ndvi_horn_of_africa",
                           "ipc_phase_reports", "wfp_food_prices_igad"],
    ),
    ModelSpec(
        id="M6",
        name="CNN — NDVI Vegetation Stress Detector",
        urn_name="cnn_ndvi_anomaly_detector",
        category="Deep Learning",
        technique="3-layer Conv2D + Global Average Pooling on NDVI time series tiles",
        output_description="Vegetation stress probability per sub-region",
        update_frequency="Weekly (Monday 06:50 UTC)",
        upstream_datasets=["modis_ndvi_horn_of_africa"],
    ),
    ModelSpec(
        id="M7",
        name="Prophet + TimeGPT — 12-Week Forecaster",
        urn_name="timegpt_12w_forecaster",
        category="Foundation Model",
        technique="NeuralProphet + Nixtla TimeGPT zero-shot, ensemble mean with 95% CI",
        output_description="12-week climate variable forecast with confidence intervals",
        update_frequency="Weekly (Monday 07:05 UTC)",
        upstream_datasets=["chirps_spi_horn_of_africa", "modis_ndvi_horn_of_africa"],
    ),
    ModelSpec(
        id="M8",
        name="VARLiNGAM — Causal Discovery Engine",
        urn_name="varlingam_causal_discovery",
        category="Causal Inference",
        technique="Linear Non-Gaussian Acyclic Model (LiNGAM) with VAR time series",
        output_description="Causal graph edges written to Neo4j — which variables cause which",
        update_frequency="Monthly (1st of month 00:00 UTC)",
        upstream_datasets=["chirps_spi_horn_of_africa", "modis_ndvi_horn_of_africa",
                           "ipc_phase_reports", "wfp_food_prices_igad", "icpac_rss_alerts"],
    ),
    ModelSpec(
        id="M9",
        name="PageRank — Vulnerability Propagation Scorer",
        urn_name="pagerank_vulnerability_scorer",
        category="Network Science",
        technique="Personalised PageRank on IGAD regional adjacency graph (weighted by crisis spillover)",
        output_description="Systemic vulnerability score = PR(i) × RiskScore(i) × Vulnerability(i)",
        update_frequency="Weekly (Monday 07:10 UTC)",
        upstream_datasets=["bma_risk_scores_weekly"],
    ),
    ModelSpec(
        id="M10",
        name="Louvain Community Detection — Aid Allocation Clusters",
        urn_name="louvain_aid_cluster_detector",
        category="Network Science",
        technique="Modularity-maximising Louvain algorithm on hazard similarity graph",
        output_description="Aid allocation clusters — groups of regions with correlated hazard profiles",
        update_frequency="Monthly (1st of month 00:00 UTC)",
        upstream_datasets=["bma_risk_scores_weekly"],
    ),
    ModelSpec(
        id="M11",
        name="SIR Cascade — Contagion Probability Model",
        urn_name="sir_contagion_cascade",
        category="Network Science",
        technique="Stochastic SIR cascade (10,000 Monte Carlo runs) on IGAD mobility graph",
        output_description="P(contagion from source region to target region within H weeks)",
        update_frequency="Weekly (Monday 07:20 UTC)",
        upstream_datasets=["bma_risk_scores_weekly"],
    ),
    ModelSpec(
        id="M12",
        name="Bayesian Model Averaging Engine",
        urn_name="bayesian_model_averaging",
        category="Ensemble",
        technique="Posterior-weighted BMA: P(crisis|data) = Σ P(crisis|data,Mm) × P(Mm|data)",
        output_description="Posterior BMA risk score [0,1] per region, updated model weights",
        update_frequency="Weekly (Monday 07:35 UTC)",
        upstream_datasets=["all_model_outputs"],
    ),
    ModelSpec(
        id="M13",
        name="Kelly Criterion Alert Prioritiser",
        urn_name="kelly_alert_prioritiser",
        category="Decision Theory",
        technique="Kelly-fractional criterion: Priority = (p×c - (1-p))/p × (1-u)",
        output_description="Ordered alert dispatch queue by Kelly-optimal priority",
        update_frequency="On-demand (pre-alert dispatch)",
        upstream_datasets=["bma_risk_scores_weekly"],
    ),
    ModelSpec(
        id="M14",
        name="GNN-PPO — Optimal Alert Dispatch Agent",
        urn_name="gnn_ppo_alert_dispatch_agent",
        category="Deep Reinforcement Learning",
        technique="Graph Attention Network (4-head, 2-layer) + Proximal Policy Optimisation",
        output_description="Optimal alert timing + targeting decisions to maximise IPC improvement "
                           "and minimise alert fatigue",
        update_frequency="Weekly training (1st of month 01:00 UTC) / Inference weekly",
        upstream_datasets=["bma_risk_scores_weekly", "alert_dispatch_log",
                           "farmer_sms_responses"],
    ),
]


def register_all_models(client) -> None:
    """Register all 14 models as DataHub MLModel entities with full metadata."""
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import MLModelPropertiesClass

    for spec in MODEL_REGISTRY:
        model_urn = MODELS[spec.id]

        props = MLModelPropertiesClass(
            description=(
                f"HazardGraph Model {spec.id}: {spec.name}\n\n"
                f"Category: {spec.category}\n"
                f"Technique: {spec.technique}\n"
                f"Output: {spec.output_description}\n"
                f"Update frequency: {spec.update_frequency}"
            ),
            customProperties={
                "model_id": spec.id,
                "category": spec.category,
                "technique": spec.technique,
                "update_frequency": spec.update_frequency,
                "bma_weight": str(spec.bma_weight) if spec.bma_weight else "pending",
                "brier_score": str(spec.brier_score) if spec.brier_score else "pending",
                "project": "HazardGraph",
                "platform": "GraphAlpha Quantitative Engine",
                "igad_region": "Horn of Africa",
            },
        )

        mcp = MetadataChangeProposalWrapper(
            entityUrn=model_urn,
            aspect=props,
        )
        client.emit(mcp)

    logger.info("Registered %d models to DataHub", len(MODEL_REGISTRY))