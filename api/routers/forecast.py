"""HazardGraph — Forecast API (stub).

Will be implemented in a future epic with LSTM and other time series models.
"""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["forecast"])


@router.get("/api/v1/forecast/lstm/{region_id}")
async def get_lstm_forecast(region_id: str):
    """Return LSTM-based forecast for a region (stub)."""
    return {"message": "not yet implemented", "region_id": region_id}


@router.get("/api/v1/forecast/ts/{region_id}/{variable}")
async def get_time_series_forecast(region_id: str, variable: str):
    """Return time series forecast for a region and variable (stub)."""
    return {"message": "not yet implemented", "region_id": region_id, "variable": variable}