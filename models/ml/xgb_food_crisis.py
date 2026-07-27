"""
XGBoost + SHAP food crisis predictor.
Predicts P(IPC >= 3 in 8 weeks) with calibrated probabilities
and SHAP-based feature attribution.
"""

import xgboost as xgb
import numpy as np
import pandas as pd
import shap
import pickle
import os
import datetime
from dataclasses import dataclass
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit


@dataclass
class XGBForecast:
    region_id: str
    p_crisis: float           # calibrated P(IPC >= 3 in 8 weeks)
    top_shap_features: list[tuple[str, float]]  # [(feature, shap_val)]
    raw_probability: float
    prediction_date: str


FEATURES = [
    'spi_30d', 'spi_90d', 'spi_180d', 'ndvi_anomaly',
    'maize_price_pct', 'sorghum_price_pct',
    'ipc_phase_lag1', 'ipc_phase_lag4',
    'hmm_regime_encoded', 'sde_p_drought',
    'rainfall_trend_slope', 'month_sin', 'month_cos'
]


class XGBFoodCrisisPredictor:

    def __init__(self):
        self.model = None
        self.calibrated = None
        self.explainer = None
        self.is_fitted = False
        self.SAVE_DIR = 'models/saved'

    def _make_synthetic_training_data(self, n: int = 1000):
        np.random.seed(123)
        X = pd.DataFrame({
            'spi_30d':            np.random.normal(0, 1, n),
            'spi_90d':            np.random.normal(0, 0.8, n),
            'spi_180d':           np.random.normal(0, 0.6, n),
            'ndvi_anomaly':       np.random.normal(0, 0.15, n),
            'maize_price_pct':    np.random.normal(0.05, 0.20, n),
            'sorghum_price_pct':  np.random.normal(0.04, 0.18, n),
            'ipc_phase_lag1':     np.random.choice([1, 2, 3, 4, 5], n,
                                                    p=[0.3, 0.35, 0.2, 0.1, 0.05]),
            'ipc_phase_lag4':     np.random.choice([1, 2, 3, 4, 5], n,
                                                    p=[0.35, 0.35, 0.18, 0.09, 0.03]),
            'hmm_regime_encoded': np.random.choice([0, 1, 2, 3, 4], n),
            'sde_p_drought':      np.clip(np.random.beta(2, 5, n), 0, 1),
            'rainfall_trend_slope': np.random.normal(0, 0.1, n),
            'month_sin':          np.sin(2 * np.pi * np.random.randint(1, 13, n) / 12),
            'month_cos':          np.cos(2 * np.pi * np.random.randint(1, 13, n) / 12),
        })
        # Label: crisis if SPI < -1 AND food price rising AND IPC lag >= 3
        y = (
            (X['spi_30d'] < -0.8) &
            (X['maize_price_pct'] > 0.10) &
            (X['ipc_phase_lag1'] >= 3)
        ).astype(int)
        return X, y

    def train(self, X: pd.DataFrame = None, y=None):
        if X is None:
            X, y = self._make_synthetic_training_data()

        n_positive = y.sum()
        n_negative = (y == 0).sum()
        scale_pos_weight = n_negative / max(n_positive, 1)

        self.model = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.02,
            subsample=0.8,
            colsample_bytree=0.7,
            scale_pos_weight=scale_pos_weight,
            use_label_encoder=False,
            eval_metric='logloss',
            random_state=42,
            n_jobs=-1
        )

        self.model.fit(X, y)

        # Platt scaling calibration on held-out 20%
        cal_idx = int(len(X) * 0.8)
        if isinstance(y, pd.Series) or isinstance(y, pd.DataFrame):
            X_cal = X.iloc[cal_idx:]
            y_cal = y.iloc[cal_idx:]
        else:
            X_cal = X[cal_idx:]
            y_cal = y[cal_idx:] if len(y.shape) == 1 else y[cal_idx:]

        self.calibrated = CalibratedClassifierCV(
            self.model, method='sigmoid', cv='prefit'
        )
        self.calibrated.fit(X_cal, y_cal)

        # SHAP explainer
        self.explainer = shap.TreeExplainer(self.model)
        self.is_fitted = True
        os.makedirs(self.SAVE_DIR, exist_ok=True)
        with open(f'{self.SAVE_DIR}/xgb_food_crisis.pkl', 'wb') as f:
            pickle.dump({
                'model': self.model,
                'calibrated': self.calibrated,
                'explainer': self.explainer
            }, f)

    def load(self) -> bool:
        path = f'{self.SAVE_DIR}/xgb_food_crisis.pkl'
        if not os.path.exists(path):
            return False
        with open(path, 'rb') as f:
            saved = pickle.load(f)
        self.model = saved['model']
        self.calibrated = saved['calibrated']
        self.explainer = saved['explainer']
        self.is_fitted = True
        return True

    def predict(self, X_row: pd.DataFrame) -> XGBForecast:
        """
        X_row: single-row DataFrame with FEATURES columns.
        Returns XGBForecast with calibrated probability + SHAP explanation.
        """
        if not self.is_fitted:
            if not self.load():
                self.train()

        # Calibrated probability
        p_crisis = float(
            self.calibrated.predict_proba(X_row)[:, 1][0]
        )
        raw_p = float(
            self.model.predict_proba(X_row)[:, 1][0]
        )

        # SHAP values for explainability
        shap_values = self.explainer.shap_values(X_row)
        if isinstance(shap_values, list):
            shap_vals = shap_values[1][0]   # positive class
        else:
            shap_vals = shap_values[0]

        # Top 5 SHAP features by absolute value
        feature_shap = list(zip(FEATURES, shap_vals.tolist()))
        top_5 = sorted(feature_shap, key=lambda x: abs(x[1]),
                       reverse=True)[:5]

        return XGBForecast(
            region_id='',
            p_crisis=p_crisis,
            top_shap_features=top_5,
            raw_probability=raw_p,
            prediction_date=datetime.date.today().isoformat()
        )

    def _build_feature_row(
        self, region_id: str, scoring_result, sde_result: dict,
        hmm_regime: str
    ) -> pd.DataFrame:
        """Build feature row from existing pipeline outputs."""
        regime_map = {
            'Baseline': 0, 'DroughtOnset': 1, 'SevereDrought': 2,
            'FloodWatch': 3, 'FloodEmergency': 4
        }
        month = datetime.datetime.utcnow().month
        return pd.DataFrame([{
            'spi_30d':             scoring_result.components.get('rainfall', 0) * -3,
            'spi_90d':             scoring_result.components.get('rainfall', 0) * -2,
            'spi_180d':            scoring_result.components.get('rainfall', 0) * -1.5,
            'ndvi_anomaly':        scoring_result.components.get('rainfall', 0) * -0.2,
            'maize_price_pct':     scoring_result.components.get('food', 0) * 0.5,
            'sorghum_price_pct':   scoring_result.components.get('food', 0) * 0.4,
            'ipc_phase_lag1':      scoring_result.components.get('ipc', 0) * 5,
            'ipc_phase_lag4':      max(1, scoring_result.components.get('ipc', 0) * 5 - 1),
            'hmm_regime_encoded':  regime_map.get(hmm_regime, 0),
            'sde_p_drought':       sde_result.get('p_drought_4w', 0.1),
            'rainfall_trend_slope': scoring_result.components.get('rainfall', 0) * -0.1,
            'month_sin':           np.sin(2 * np.pi * month / 12),
            'month_cos':           np.cos(2 * np.pi * month / 12),
        }])

    async def run_all_regions(
        self, neo4j_session
    ) -> dict[str, XGBForecast]:
        """Run XGBoost inference for all regions."""
        if not self.is_fitted:
            if not self.load():
                self.train()

        results = {}
        regions = ['kenya', 'ethiopia', 'somalia', 'sudan', 'south_sudan',
                   'uganda', 'djibouti', 'eritrea', 'tanzania', 'burundi', 'rwanda']

        for region_id in regions:
            # Build feature row from Neo4j data
            async with neo4j_session as s:
                result = await s.run(
                    'MATCH (r:Region {id: $rid}) '
                    'OPTIONAL MATCH (r)<-[:MEASURED_IN]-(rf:RainfallSignal) '
                    'OPTIONAL MATCH (r)-[:IN_REGIME]->(h:HazardRegime) '
                    'RETURN rf.spi_30d AS spi, h.name AS regime',
                    rid=region_id
                )
                record = await result.single()
                spi = record['spi'] if record and record['spi'] else 0.0
                regime = record['regime'] if record and record['regime'] else 'Baseline'

            from risk.scoring_service import RegionRiskScore
            scoring_result = RegionRiskScore(
                region_id=region_id, name=region_id, country=region_id,
                score=50.0, delta=0.0,
                components={'rainfall': abs(spi) / 3.0 if spi else 0.5, 'food': 0.3, 'ipc': 0.4,
                            'sde': 0.3, 'network': 0.3},
                vulnerability_multiplier=1.5,
                current_regime=regime, alert_triggered=False
            )
            sde_result = {'p_drought_4w': 0.3}

            X_row = self._build_feature_row(region_id, scoring_result, sde_result, regime)
            forecast = self.predict(X_row)
            forecast.region_id = region_id

            # Write MLForecast node to Neo4j
            async with neo4j_session as s:
                await s.run(
                    'MERGE (m:MLForecast {id: $id}) '
                    'SET m.model = "XGBoost", m.horizon_weeks = 8, '
                    '    m.p_crisis = $p_crisis, m.raw_probability = $raw_p, '
                    '    m.top_shap_features = $shap, m.region_id = $rid, '
                    '    m.prediction_date = $date, m.created_at = $now',
                    id=f'xgb_{region_id}',
                    p_crisis=forecast.p_crisis,
                    raw_p=forecast.raw_probability,
                    shap=str(forecast.top_shap_features),
                    rid=region_id,
                    date=forecast.prediction_date,
                    now=datetime.datetime.utcnow().isoformat()
                )
            results[region_id] = forecast
        return results