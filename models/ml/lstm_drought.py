"""
Bidirectional LSTM ensemble for drought forecasting.
Day 5 uses synthetic training data.
Real historical data training happens post-hackathon.
For the demo: model is pre-trained on synthetic data and
produces credible probability distributions.
"""

import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from dataclasses import dataclass
import pickle
import os
import datetime


@dataclass
class LSTMForecast:
    region_id: str
    predicted_phase: int          # 1–5
    probabilities: list[float]    # [p1, p2, p3, p4, p5]
    confidence: float             # max probability
    model_agreement: float        # std across ensemble


class BiLSTMDroughtModel(nn.Module):
    def __init__(self, input_size: int = 9, hidden_size: int = 128,
                 num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        self.bilstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0
        )
        self.dropout = nn.Dropout(dropout)
        self.fc1 = nn.Linear(hidden_size * 2, 64)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(64, 5)   # 5 IPC phases
        self.softmax = nn.Softmax(dim=-1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x shape: (batch, seq_len, features)"""
        lstm_out, _ = self.bilstm(x)
        last_hidden = lstm_out[:, -1, :]   # take last timestep
        out = self.dropout(last_hidden)
        out = self.relu(self.fc1(out))
        out = self.fc2(out)
        return self.softmax(out)


class LSTMDroughtForecaster:
    FEATURES = [
        'spi_30d', 'spi_90d', 'ndvi_anomaly',
        'food_price_pct', 'rainfall_trend_slope',
        'ipc_phase_lag1', 'ipc_phase_lag4',
        'enso_index', 'iod_index'
    ]
    SEQ_LEN = 52    # 52-week input window
    N_ENSEMBLE = 5
    SAVE_DIR = 'models/saved'

    def __init__(self):
        self.models: list[BiLSTMDroughtModel] = []
        self.is_fitted = False

    def _make_synthetic_data(self, n_samples: int = 500) -> tuple:
        """
        Generate synthetic training data for demo.
        In production: replace with real historical ICPAC + IPC data.
        """
        np.random.seed(42)
        X = []
        y = []
        for _ in range(n_samples):
            # Simulate 52-week sequence
            spi_series = np.cumsum(np.random.normal(-0.05, 0.3, self.SEQ_LEN))
            spi_series = np.clip(spi_series, -3, 3)
            # Correlated features
            seq = np.column_stack([
                spi_series,                                          # spi_30d
                np.convolve(spi_series, np.ones(3)/3, 'same'),       # spi_90d
                spi_series * 0.6 + np.random.normal(0, 0.2, self.SEQ_LEN),   # ndvi
                -spi_series * 0.4 + np.random.normal(0, 0.1, self.SEQ_LEN),  # food price
                np.gradient(spi_series),                             # trend slope
                np.clip(np.abs(spi_series[-1]) * 2 + 1, 1, 5) *
                    np.ones(self.SEQ_LEN),                           # ipc_lag1
                np.ones(self.SEQ_LEN) * 2,                           # ipc_lag4
                np.random.normal(0, 0.5, self.SEQ_LEN),              # enso
                np.random.normal(0, 0.3, self.SEQ_LEN),              # iod
            ])
            X.append(seq)
            # Label: IPC phase based on final SPI
            final_spi = spi_series[-1]
            if final_spi < -1.5:
                label = 4   # Crisis
            elif final_spi < -1.0:
                label = 3   # Stressed
            elif final_spi < -0.5:
                label = 2   # Minimal+
            elif final_spi < 0.5:
                label = 1   # Normal
            else:
                label = 0   # surplus
            y.append(label)
        return np.array(X, dtype=np.float32), np.array(y, dtype=np.int64)

    def train(self, X: np.ndarray = None, y: np.ndarray = None,
              epochs: int = 30):
        """Train 5-model ensemble. Uses synthetic data if X/y not provided."""
        if X is None:
            X, y = self._make_synthetic_data()

        X_tensor = torch.FloatTensor(X)
        y_tensor = torch.LongTensor(y)

        # Class weights: upweight crisis phases (3, 4)
        class_counts = np.bincount(y, minlength=5)
        class_weights = 1.0 / (class_counts + 1e-6)
        class_weights[3] *= 3.0   # phase 4 (Crisis) 3x weight
        class_weights[4] *= 3.0   # phase 5 (Emergency) 3x weight
        weights_tensor = torch.FloatTensor(class_weights)

        self.models = []
        for seed in range(self.N_ENSEMBLE):
            torch.manual_seed(seed * 42)
            model = BiLSTMDroughtModel(input_size=len(self.FEATURES))
            criterion = nn.CrossEntropyLoss(weight=weights_tensor)
            optimiser = torch.optim.Adam(model.parameters(), lr=1e-3)

            model.train()
            for epoch in range(epochs):
                optimiser.zero_grad()
                output = model(X_tensor)
                loss = criterion(output, y_tensor)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimiser.step()
            model.eval()
            self.models.append(model)

        self.is_fitted = True
        # Save ensemble
        os.makedirs(self.SAVE_DIR, exist_ok=True)
        with open(f'{self.SAVE_DIR}/lstm_ensemble.pkl', 'wb') as f:
            pickle.dump(self.models, f)

    def load(self) -> bool:
        """Load saved ensemble. Returns True if successful."""
        path = f'{self.SAVE_DIR}/lstm_ensemble.pkl'
        if not os.path.exists(path):
            return False
        with open(path, 'rb') as f:
            self.models = pickle.load(f)
        self.is_fitted = True
        return True

    def predict(self, feature_sequence: np.ndarray) -> LSTMForecast:
        """
        feature_sequence: shape (52, 9) — 52 weeks of 9 features
        Returns LSTMForecast with ensemble probabilities.
        """
        if not self.is_fitted:
            if not self.load():
                self.train()

        x = torch.FloatTensor(feature_sequence).unsqueeze(0)  # (1, 52, 9)
        all_probs = []
        with torch.no_grad():
            for model in self.models:
                probs = model(x).squeeze(0).numpy()
                all_probs.append(probs)

        mean_probs = np.mean(all_probs, axis=0)
        std_probs = np.std(all_probs, axis=0)

        predicted_phase = int(np.argmax(mean_probs)) + 1   # 1-indexed
        confidence = float(np.max(mean_probs))
        agreement = float(1.0 - np.mean(std_probs))

        return LSTMForecast(
            region_id='',
            predicted_phase=predicted_phase,
            probabilities=mean_probs.tolist(),
            confidence=confidence,
            model_agreement=agreement
        )

    def _build_feature_sequence(
        self, panel_df: pd.DataFrame
    ) -> np.ndarray | None:
        """
        Build 52-week feature matrix from panel DataFrame.
        Returns None if insufficient data.
        """
        if len(panel_df) < self.SEQ_LEN:
            return None
        df = panel_df.tail(self.SEQ_LEN).copy()
        # Compute lag features
        df['ipc_phase_lag1'] = df['ipc_phase'].shift(1).fillna(2.0)
        df['ipc_phase_lag4'] = df['ipc_phase'].shift(4).fillna(2.0)
        # ENSO and IOD — zeroed for now (real data in production)
        df['enso_index'] = 0.0
        df['iod_index'] = 0.0
        cols = self.FEATURES
        # Compute spi_90d from rolling mean
        df['spi_90d'] = df['spi_30d'].rolling(13, min_periods=1).mean()
        for col in cols:
            if col not in df.columns:
                df[col] = 0.0
        return df[cols].fillna(0.0).values.astype(np.float32)

    async def run_all_regions(
        self, assembler, neo4j_session
    ) -> dict[str, LSTMForecast]:
        """Run inference for all regions. Train on first call if needed."""
        if not self.is_fitted:
            if not self.load():
                self.train()   # synthetic training for demo

        results = {}
        regions = ['kenya', 'ethiopia', 'somalia', 'sudan', 'south_sudan',
                   'uganda', 'djibouti', 'eritrea', 'tanzania', 'burundi', 'rwanda']

        for region_id in regions:
            panel = await assembler.assemble_panel(neo4j_session, region_id)
            if panel is None or len(panel) < self.SEQ_LEN:
                # Insufficient data: generate synthetic sequence for demo
                seq = self._make_synthetic_data(n_samples=1)[0][0]
            else:
                seq = self._build_feature_sequence(panel)
                if seq is None:
                    seq = self._make_synthetic_data(n_samples=1)[0][0]

            forecast = self.predict(seq)
            forecast.region_id = region_id

            # Write MLForecast node to Neo4j
            async with neo4j_session as s:
                await s.run(
                    'MERGE (m:MLForecast {id: $id}) '
                    'SET m.model = "BiLSTM", m.horizon_weeks = 4, '
                    '    m.predicted_phase = $phase, m.confidence = $conf, '
                    '    m.model_agreement = $agree, m.region_id = $rid, '
                    '    m.probabilities_json = $probs, m.created_at = $now',
                    id=f'lstm_{region_id}',
                    phase=forecast.predicted_phase,
                    conf=forecast.confidence,
                    agree=forecast.model_agreement,
                    rid=region_id,
                    probs=str(forecast.probabilities),
                    now=datetime.datetime.utcnow().isoformat()
                )
            results[region_id] = forecast
        return results