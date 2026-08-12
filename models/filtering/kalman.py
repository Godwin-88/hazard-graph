"""HazardGraph — Scalar linear Kalman filter for smoothing SPI time series.

Uses only numpy — no external Kalman library.
State vector: x = [level, trend] (2D)
F = [[1, 1], [0, 1]]  (constant velocity model)
H = [1, 0]            (observe level only)
"""

import logging
import numpy as np
from typing import Tuple, List

from db.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


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

    async def smooth_all(self) -> dict:
        """Smooth SPI series for all regions and write back to Neo4j.

        Queries all RainfallSignal nodes grouped by region, applies the
        Kalman filter to each region's SPI series (ordered by date), and
        updates the `spi_30d_smoothed` property on each node.

        Returns a summary dict with counts.
        """
        summary = {"total": 0, "updated": 0, "failed": 0, "skipped": 0}

        try:
            # Fetch all rainfall signals ordered by region and date
            rows = await neo4j_client.execute_read(
                """
                MATCH (rs:RainfallSignal)
                RETURN rs.region_id AS region_id,
                       rs.id AS signal_id,
                       rs.spi_30d AS spi_30d,
                       rs.date AS date
                ORDER BY rs.region_id, rs.date ASC
                """
            )

            # Group by region preserving chronological order
            from collections import OrderedDict
            by_region: "OrderedDict[str, list]" = OrderedDict()
            for row in rows:
                region_id = row.get("region_id")
                if not region_id:
                    continue
                by_region.setdefault(region_id, []).append(row)

            summary["total"] = len(rows)

            for region_id, region_rows in by_region.items():
                try:
                    series = []
                    for r in region_rows:
                        try:
                            series.append(float(r.get("spi_30d") or 0.0))
                        except (TypeError, ValueError):
                            series.append(0.0)

                    if len(series) < 2:
                        summary["skipped"] += 1
                        continue

                    # Apply Kalman smoothing to the full series
                    smoothed = self.smooth_series(series)

                    # Batch-write smoothed values in a single transaction
                    updates = [
                        {"id": r["signal_id"], "smoothed": round(value, 4)}
                        for r, value in zip(region_rows, smoothed)
                    ]
                    if updates:
                        await neo4j_client.execute_write(
                            """
                            UNWIND $updates AS u
                            MATCH (rs:RainfallSignal {id: u.id})
                            SET rs.spi_30d_smoothed = u.smoothed
                            """,
                            {"updates": updates},
                        )
                    summary["updated"] += len(region_rows)
                    logger.info(
                        "Kalman smoothed %d signals for %s",
                        len(region_rows),
                        region_id,
                    )
                except Exception as exc:
                    summary["failed"] += 1
                    logger.error("Kalman smoothing failed for %s: %s", region_id, exc)

        except Exception as exc:
            logger.error("Kalman smooth_all failed: %s", exc)

        logger.info(
            "Kalman smoothing complete: %d updated, %d failed, %d skipped (of %d rows)",
            summary["updated"],
            summary["failed"],
            summary["skipped"],
            summary["total"],
        )
        return summary
