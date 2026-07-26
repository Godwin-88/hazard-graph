"""HazardGraph — HMM trainer orchestrator.

Assembles panel data per region, trains ClimateHMM, and saves
fitted models to disk.
"""

import logging
import os
from typing import Optional

import pandas as pd

from causal.time_series_assembler import assemble_panel
from models.regime.climate_hmm import ClimateHMM

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models", "saved")


def _ensure_models_dir() -> None:
    """Create the models/saved directory if it doesn't exist."""
    os.makedirs(MODELS_DIR, exist_ok=True)


def _model_path(region_id: str) -> str:
    """Get the file path for a saved HMM model."""
    return os.path.join(MODELS_DIR, f"hmm_{region_id}.pkl")


async def train_for_region(region_id: str) -> Optional[ClimateHMM]:
    """Train a ClimateHMM for a single region.

    Steps:
    1. Assemble panel data (104 weeks lookback)
    2. Check data sufficiency
    3. Fit ClimateHMM
    4. Save to disk

    Returns:
        Fitted ClimateHMM, or None if insufficient data.
    """
    _ensure_models_dir()

    df = await assemble_panel(region_id, lookback_weeks=104)
    if df is None:
        logger.warning("No panel data available for region %s", region_id)
        return None

    hmm = ClimateHMM()
    if not hmm.is_data_sufficient(df):
        logger.warning("Insufficient data for HMM training in region %s: %d rows", region_id, len(df))
        return None

    try:
        hmm.fit(df)
        hmm.save(_model_path(region_id))
        logger.info("HMM trained and saved for region %s", region_id)
        return hmm
    except Exception as exc:
        logger.error("HMM training failed for region %s: %s", region_id, exc)
        return None


async def load_or_train(region_id: str) -> Optional[ClimateHMM]:
    """Load a fitted HMM from disk, or train one if not found.

    Returns:
        Fitted ClimateHMM, or None if training fails.
    """
    path = _model_path(region_id)
    if os.path.exists(path):
        try:
            hmm = ClimateHMM.load(path)
            logger.info("Loaded existing HMM for region %s", region_id)
            return hmm
        except Exception as exc:
            logger.warning("Failed to load HMM for %s, retraining: %s", region_id, exc)

    return await train_for_region(region_id)