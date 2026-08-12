"""HazardGraph — Central DataHub entity URN definitions.

All dataset and ML model URNs are defined here so that the model
registry, dataset registry, lineage, and agent tools all reference
the same canonical entity identifiers.
"""

# ── DATASET URNS ──────────────────────────────────────────────────────────────
DATASETS = {
    "chirps":       "urn:li:dataset:(urn:li:dataPlatform:chirps,chirps_spi_horn_of_africa,PROD)",
    "modis":        "urn:li:dataset:(urn:li:dataPlatform:nasa,modis_ndvi_horn_of_africa,PROD)",
    "ipc":          "urn:li:dataset:(urn:li:dataPlatform:ipc,ipc_phase_reports_igad,PROD)",
    "wfp":          "urn:li:dataset:(urn:li:dataPlatform:wfp,wfp_food_prices_igad,PROD)",
    "icpac":        "urn:li:dataset:(urn:li:dataPlatform:icpac,icpac_rss_alerts,PROD)",
    "bma_scores":   "urn:li:dataset:(urn:li:dataPlatform:hazardgraph,bma_risk_scores_weekly,PROD)",
    "alerts":       "urn:li:dataset:(urn:li:dataPlatform:hazardgraph,alert_dispatch_log,PROD)",
    "sms_feedback": "urn:li:dataset:(urn:li:dataPlatform:hazardgraph,farmer_sms_responses,PROD)",
    "all_model_outputs": "urn:li:dataset:(urn:li:dataPlatform:hazardgraph,all_model_outputs,PROD)",
}

# ── MODEL URNS ────────────────────────────────────────────────────────────────
_MODEL_NAMES = [
    "cir_jump_diffusion_rainfall",       # M1
    "hidden_markov_regime_detector",      # M2
    "kalman_filter_spi_smoother",         # M3
    "bilstm_drought_forecaster",          # M4
    "xgb_food_crisis_predictor",          # M5
    "cnn_ndvi_anomaly_detector",          # M6
    "timegpt_12w_forecaster",             # M7
    "varlingam_causal_discovery",         # M8
    "pagerank_vulnerability_scorer",      # M9
    "louvain_aid_cluster_detector",       # M10
    "sir_contagion_cascade",              # M11
    "bayesian_model_averaging",           # M12
    "kelly_alert_prioritiser",            # M13
    "gnn_ppo_alert_dispatch_agent",       # M14
]

MODELS = {
    f"M{i}": f"urn:li:mlModel:(urn:li:dataPlatform:hazardgraph,{name},PROD)"
    for i, name in enumerate(_MODEL_NAMES, start=1)
}

# ── DATASET METADATA (for dataset_registry) ──────────────────────────────────
DATASET_SPECS = [
    {
        "key": "chirps",
        "name": "chirps_spi_horn_of_africa",
        "platform": "chirps",
        "description": "CHIRPS rainfall SPI (Standardised Precipitation Index) for the Horn of Africa. "
                       "Daily rainfall estimates from UCSB CHC, aggregated to weekly SPI per IGAD sub-region.",
        "update_frequency": "Daily",
        "owner": "UCSB Climate Hazards Center",
    },
    {
        "key": "modis",
        "name": "modis_ndvi_horn_of_africa",
        "platform": "nasa",
        "description": "MODIS NDVI (Normalised Difference Vegetation Index) 250m tiles for the Horn of Africa. "
                       "Weekly vegetation greenness anomaly per IGAD sub-region.",
        "update_frequency": "Weekly",
        "owner": "NASA Earthdata",
    },
    {
        "key": "ipc",
        "name": "ipc_phase_reports_igad",
        "platform": "ipc",
        "description": "IPC Acute Food Insecurity phase classifications (1-5) for IGAD countries. "
                       "Official phase reports from the Integrated Food Security Phase Classification.",
        "update_frequency": "Monthly",
        "owner": "IPC Global Initiative",
    },
    {
        "key": "wfp",
        "name": "wfp_food_prices_igad",
        "platform": "wfp",
        "description": "WFP DataBridges food price data for IGAD countries. "
                       "Weekly market prices for staple commodities.",
        "update_frequency": "Weekly",
        "owner": "World Food Programme",
    },
    {
        "key": "icpac",
        "name": "icpac_rss_alerts",
        "platform": "icpac",
        "description": "ICPAC RSS feed alerts for the Greater Horn of Africa. "
                       "Climate advisories, seasonal forecasts, and hazard warnings.",
        "update_frequency": "Daily",
        "owner": "ICPAC",
    },
    {
        "key": "bma_scores",
        "name": "bma_risk_scores_weekly",
        "platform": "hazardgraph",
        "description": "Weekly Bayesian Model Averaging posterior risk scores [0,1] per IGAD sub-region. "
                       "Fusion of all 14 HazardGraph model outputs.",
        "update_frequency": "Weekly (Monday 07:35 UTC)",
        "owner": "HazardGraph / Quantifaya",
    },
    {
        "key": "alerts",
        "name": "alert_dispatch_log",
        "platform": "hazardgraph",
        "description": "Log of all dispatched food security alerts. "
                       "Contains alert ID, region, message text, dispatch timestamp, and delivery status.",
        "update_frequency": "On-demand",
        "owner": "HazardGraph / Quantifaya",
    },
    {
        "key": "sms_feedback",
        "name": "farmer_sms_responses",
        "platform": "hazardgraph",
        "description": "Farmer SMS Y/N responses to dispatched alerts. "
                       "Used as the GNN-PPO training reward signal and BMA weight updater.",
        "update_frequency": "Real-time",
        "owner": "HazardGraph / Quantifaya",
    },
    {
        "key": "all_model_outputs",
        "name": "all_model_outputs",
        "platform": "hazardgraph",
        "description": "Consolidated output table of all 14 HazardGraph model predictions. "
                       "Used by the BMA engine and model performance tracking.",
        "update_frequency": "Weekly",
        "owner": "HazardGraph / Quantifaya",
    },
]