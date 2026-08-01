"""HazardGraph — Forecast API with LSTM, XGBoost, and aggregate endpoints."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from neo4j import AsyncManagedTransaction

from auth.jwt_service import get_current_user
from db.neo4j_client import get_neo4j_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["forecast"])


@router.get("/forecast/lstm/{region_id}")
async def get_lstm_forecast(
    region_id: str,
    neo4j_session=Depends(get_neo4j_session),
    _user=Depends(get_current_user),
):
    """Return latest MLForecast node from Neo4j for LSTM model."""
    async with neo4j_session as session:
        result = await session.run(
            'MATCH (m:MLForecast {id: $id}) '
            'RETURN m.predicted_phase AS phase, m.confidence AS conf, '
            '       m.model_agreement AS agreement, m.probabilities_json AS probs, '
            '       m.created_at AS created_at',
            id=f'lstm_{region_id}'
        )
        record = await result.single()

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No LSTM forecast found for region: {region_id}"
        )

    return {
        'region_id': region_id,
        'model': 'BiLSTM',
        'predicted_phase': record['phase'],
        'confidence': record['conf'],
        'model_agreement': record['agreement'],
        'probabilities': record['probs'],
        'created_at': record['created_at'],
    }


@router.get("/forecast/xgb/{region_id}")
async def get_xgb_forecast(
    region_id: str,
    neo4j_session=Depends(get_neo4j_session),
    _user=Depends(get_current_user),
):
    """Return XGBForecast from latest run."""
    async with neo4j_session as session:
        result = await session.run(
            'MATCH (m:MLForecast {id: $id}) '
            'RETURN m.p_crisis AS p_crisis, m.raw_probability AS raw_p, '
            '       m.top_shap_features AS shap, m.prediction_date AS date, '
            '       m.created_at AS created_at',
            id=f'xgb_{region_id}'
        )
        record = await result.single()

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No XGBoost forecast found for region: {region_id}"
        )

    return {
        'region_id': region_id,
        'model': 'XGBoost',
        'p_crisis': record['p_crisis'],
        'raw_probability': record['raw_p'],
        'top_shap_features': record['shap'],
        'prediction_date': record['date'],
        'created_at': record['created_at'],
    }


@router.get("/forecast/all/{region_id}")
async def get_all_forecasts(
    region_id: str,
    neo4j_session=Depends(get_neo4j_session),
    _user=Depends(get_current_user),
):
    """Aggregate: LSTM + XGBoost + SDE + BMA for region."""
    async with neo4j_session as session:
        # LSTM
        lstm_result = await session.run(
            'MATCH (m:MLForecast {id: $id}) '
            'RETURN m.predicted_phase AS phase, m.confidence AS conf, '
            '       m.probabilities_json AS probs',
            id=f'lstm_{region_id}')
        lstm = await lstm_result.single()

        # XGBoost
        xgb_result = await session.run(
            'MATCH (m:MLForecast {id: $id}) '
            'RETURN m.p_crisis AS p_crisis, m.top_shap_features AS shap',
            id=f'xgb_{region_id}')
        xgb = await xgb_result.single()

        # SDE
        sde_result = await session.run(
            'MATCH (s:StochasticSignal {region_id: $rid}) '
            'RETURN s.p_drought_4w AS p_drought, s.p_flood_4w AS p_flood, '
            '       s.p_severe_4w AS p_severe '
            'ORDER BY s.created_at DESC LIMIT 1',
            rid=region_id)
        sde = await sde_result.single()

        # BMA score
        bma_result = await session.run(
            'MATCH (b:BMAScore {region_id: $rid}) '
            'RETURN b.total_score AS score, b.model_weights_json AS weights '
            'ORDER BY b.created_at DESC LIMIT 1',
            rid=region_id)
        bma = await bma_result.single()

    payload = {
        'region_id': region_id,
        'lstm': {
            'predicted_phase': lstm['phase'] if lstm else None,
            'confidence': lstm['conf'] if lstm else None,
        } if lstm else None,
        'xgboost': {
            'p_crisis': xgb['p_crisis'] if xgb else None,
        } if xgb else None,
        'sde': {
            'p_drought': sde['p_drought'] if sde else None,
            'p_flood': sde['p_flood'] if sde else None,
        } if sde else None,
        'bma': {
            'score': bma['score'] if bma else None,
        } if bma else None,
    }

    # Demo fallback: if no forecast nodes exist for the region, return a
    # plausible seeded forecast so the UI never shows all-N/A charts on a
    # fresh DB. Marked as demo so the frontend can show a hint if desired.
    if not lstm and not xgb and not sde and not bma:
        r = hash(region_id) % 10
        payload = {
            'region_id': region_id,
            'lstm': {
                'predicted_phase': 2 + (r % 3),
                'confidence': 0.62 + (r % 20) / 100.0,
                'model_agreement': 0.05 + (r % 40) / 100.0,
            },
            'xgboost': {
                'p_crisis': 0.12 + (r % 55) / 100.0,
                'top_shap_features': ['rainfall', 'food_prices'],
            },
            'sde': {
                'p_drought': 0.08 + (r % 35) / 100.0,
                'p_flood': 0.02 + ((r + 3) % 20) / 100.0,
            },
            'bma': {
                'score': 20 + r * 6,
                'weights': {'lstm': 0.3, 'xgb': 0.3, 'sde': 0.2, 'hmm': 0.2},
            },
            'source': 'demo',
        }

    return payload
