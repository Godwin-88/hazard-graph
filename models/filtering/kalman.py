"""HazardGraph — Scalar linear Kalman filter for smoothing SPI time series.

Uses only numpy — no external Kalman library.
State vector: x = [level, trend] (2D)
F = [[1, 1], [0, 1]]  (constant velocity model)
H = [1, 0]            (observe level only)
"""

import numpy as np
from typing import Tuple, List


class KalmanSmoother:
    """Scalar linear Kalman filter for SPI time series smoothing.

    Process noise Q controls how much the state can change between steps.
    Measurement noise R controls how much we trust each observation.
    """

    def __init__(self, process_noise: float = 0.1, measurement_noise: float = 0.5):
        self.Q = process_noise  # state transition noise variance
        self.R = measurement_noise  # measurement noise variance

        # State transition matrix (constant velocity model)
        self.F = np.array([[1.0, 1.0], [0.0, 1.0]])

        # Observation matrix (observe level only)
        self.H = np.array([[1.0, 0.0]])

        # State vector: [level, trend]
        self.x = np.array([[0.0], [0.0]])

        # Error covariance
        self.P = np.eye(2) * 1.0

        self._initialised = False

    def reset(self) -> None:
        """Reset filter state for a new region."""
        self.x = np.array([[0.0], [0.0]])
        self.P = np.eye(2) * 1.0
        self._initialised = False

    def update(self, z: float) -> Tuple[float, float]:
        """Process one observation z.

        Returns:
            (smoothed_level, innovation)
            innovation = z - H @ x_pred (large = data quality flag)
        """
        # Predict
        x_pred = self.F @ self.x
        P_pred = self.F @ self.P @ self.F.T + self.Q * np.eye(2)

        # Innovation (residual)
        innovation = z - (self.H @ x_pred).item()

        # Kalman gain
        S = (self.H @ P_pred @ self.H.T).item() + self.R
        K = (P_pred @ self.H.T) / S

        # Update
        self.x = x_pred + K * innovation
        self.P = (np.eye(2) - K @ self.H) @ P_pred

        self._initialised = True

        return float(self.x[0, 0]), float(innovation)

    def smooth_series(self, series: List[float]) -> List[float]:
        """Apply filter to full series, return smoothed values.

        Creates a fresh filter instance internally so this is stateless
        between calls. Use for batch processing.
        """
        smoother = KalmanSmoother(process_noise=self.Q, measurement_noise=self.R)
        smoothed = []
        for z in series:
            level, _ = smoother.update(z)
            smoothed.append(level)
        return smoothed

    def flag_anomaly(self, innovation: float, threshold: float = 2.5) -> bool:
        """Return True if |innovation| > threshold (data quality issue)."""
        return abs(innovation) > threshold