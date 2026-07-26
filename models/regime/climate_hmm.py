"""HazardGraph — Climate HMM for regime detection.

Uses hmmlearn.GaussianHMM with 5 hidden states corresponding to
climate regimes: Baseline, DroughtOnset, SevereDrought,
FloodWatch, FloodEmergency.
"""

import logging
import pickle
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ClimateHMM:
    """Hidden Markov Model for climate regime detection.

    Models 5 climate regimes from SPi, food prices, IPC phase,
    and rainfall trend features.
    """

    N_STATES = 5
    STATE_NAMES = ["Baseline", "DroughtOnset", "SevereDrought", "FloodWatch", "FloodEmergency"]
    FEATURES = ["spi_30d", "food_price_pct_change", "ipc_phase", "rainfall_trend_slope"]

    def __init__(self):
        try:
            from hmmlearn import hmm
            self.model = hmm.GaussianHMM(
                n_components=self.N_STATES,
                covariance_type="diag",
                n_iter=200,
                random_state=42,
                tol=1e-4,
            )
        except ImportError:
            logger.error("hmmlearn not installed. Install with: pip install hmmlearn")
            raise

        self.is_fitted = False
        self.state_name_map: Dict[int, str] = {}

    def fit(self, df: pd.DataFrame) -> None:
        """Train the HMM on historical data.

        After fitting, assigns human-readable state labels by
        examining emission means per state.

        Args:
            df: DataFrame with columns matching FEATURES.
        """
        # Prepare feature matrix
        available = [f for f in self.FEATURES if f in df.columns]
        if len(available) < 2:
            raise ValueError(f"Need at least 2 features, got {available}")

        X = df[available].dropna().values

        if len(X) < self.N_STATES * 10:
            raise ValueError(
                f"Too few samples for HMM: {len(X)} (need at least {self.N_STATES * 10})"
            )

        # Fit the model
        self.model.fit(X)
        self.is_fitted = True

        # Assign state names by heuristic analysis of emission means
        self._assign_state_names(available)

        logger.info("ClimateHMM fitted on %d samples with %d features", len(X), len(available))

    def _assign_state_names(self, feature_names: List[str]) -> None:
        """Map state indices to human-readable names based on emission means.

        Heuristic:
        - State with lowest SPI mean → SevereDrought
        - State with highest SPI mean → FloodEmergency / FloodWatch
        - State with highest food_price_pct_change → SevereDrought (confirm)
        - State with lowest ipc_phase mean → Baseline
        - Remaining → DroughtOnset or FloodWatch by SPI ranking
        """
        means = self.model.means_  # shape: (N_STATES, n_features)

        # Build feature index map
        try:
            spi_idx = feature_names.index("spi_30d")
            price_idx = feature_names.index("food_price_pct_change")
            ipc_idx = feature_names.index("ipc_phase")
        except ValueError:
            spi_idx = 0
            price_idx = min(1, len(feature_names) - 1)
            ipc_idx = min(2, len(feature_names) - 1)

        spi_means = means[:, spi_idx]
        price_means = means[:, price_idx] if len(feature_names) > price_idx else np.zeros(self.N_STATES)
        ipc_means = means[:, ipc_idx] if len(feature_names) > ipc_idx else np.zeros(self.N_STATES)

        # Rank states by SPI
        spi_ranking = np.argsort(spi_means)  # 0 = lowest SPI, 4 = highest SPI

        # Assign names
        assigned = set()
        self.state_name_map = {}

        # Lowest SPI → SevereDrought
        severe_drought_state = spi_ranking[0]
        self.state_name_map[int(severe_drought_state)] = "SevereDrought"
        assigned.add(int(severe_drought_state))

        # Highest SPI → FloodEmergency
        flood_emergency_state = spi_ranking[-1]
        self.state_name_map[int(flood_emergency_state)] = "FloodEmergency"
        assigned.add(int(flood_emergency_state))

        # Second highest SPI → FloodWatch
        flood_watch_state = spi_ranking[-2]
        if int(flood_watch_state) not in assigned:
            self.state_name_map[int(flood_watch_state)] = "FloodWatch"
            assigned.add(int(flood_watch_state))

        # Lowest IPC phase → Baseline
        remaining = [s for s in range(self.N_STATES) if s not in assigned]
        if remaining:
            ipc_of_remaining = [(s, ipc_means[s]) for s in remaining]
            ipc_of_remaining.sort(key=lambda x: x[1])
            baseline_state = ipc_of_remaining[0][0]
            self.state_name_map[int(baseline_state)] = "Baseline"
            assigned.add(baseline_state)

            # Remaining → DroughtOnset
            for s in remaining:
                if s not in assigned:
                    self.state_name_map[int(s)] = "DroughtOnset"
                    assigned.add(s)

        # If any still unassigned (shouldn't happen with 5 states), fill remaining
        for s in range(self.N_STATES):
            if s not in self.state_name_map:
                self.state_name_map[s] = "DroughtOnset"

        logger.info("State name mapping: %s", self.state_name_map)

    def predict_regime(self, df: pd.DataFrame) -> Tuple[str, Dict[str, float]]:
        """Run Viterbi decoding on the data.

        Args:
            df: DataFrame with columns matching FEATURES.

        Returns:
            (current_regime_name, posterior_probabilities_dict)
        """
        if not self.is_fitted:
            raise RuntimeError("HMM not fitted. Call fit() first.")

        available = [f for f in self.FEATURES if f in df.columns]
        X = df[available].dropna().values

        if len(X) == 0:
            return "Baseline", {"Baseline": 1.0}

        # Viterbi path
        hidden_states = self.model.predict(X)
        current_state = int(hidden_states[-1])

        # Posterior probabilities for latest observation
        posteriors = self.model.predict_proba(X)
        latest_posteriors = posteriors[-1]

        # Build named posterior dict
        posterior_dict: Dict[str, float] = {}
        for i in range(self.N_STATES):
            name = self.state_name_map.get(i, f"State_{i}")
            posterior_dict[name] = round(float(latest_posteriors[i]), 4)

        current_regime = self.state_name_map.get(current_state, f"Unknown_{current_state}")

        return current_regime, posterior_dict

    def is_data_sufficient(self, df: pd.DataFrame) -> bool:
        """Check if there is enough data for reliable HMM inference.

        Minimum 104 rows (2 years weekly) required.
        """
        return len(df) >= 104

    def save(self, path: str) -> None:
        """Save the fitted model to disk as pickle."""
        with open(path, "wb") as f:
            pickle.dump(self, f)
        logger.info("ClimateHMM saved to %s", path)

    @staticmethod
    def load(path: str) -> "ClimateHMM":
        """Load a fitted model from disk."""
        with open(path, "rb") as f:
            model = pickle.load(f)
        logger.info("ClimateHMM loaded from %s", path)
        return model