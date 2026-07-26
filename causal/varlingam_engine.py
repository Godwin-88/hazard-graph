"""HazardGraph — VARLiNGAM causal discovery engine.

Uses the lingam library to discover causal relationships between
climate and food security variables from assembled panel data.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np
import pandas as pd

from db.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


@dataclass
class CausalEdgeResult:
    """Represents a discovered causal edge."""
    source_variable: str
    target_variable: str
    weight: float
    lag_weeks: int
    p_value: float
    region_id: str
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class VARLiNGAMEngine:
    """Causal discovery using VARLiNGAM with bootstrap p-values."""

    VARIABLES = ["spi_30d", "food_price_pct_change", "ipc_phase", "rainfall_trend_slope"]
    MIN_WEIGHT = 0.15
    MAX_P_VALUE = 0.05
    MAX_LAGS = 4  # 4-week maximum causal lag
    N_BOOTSTRAP = 50

    async def discover(
        self,
        df: pd.DataFrame,
        region_id: str,
    ) -> List[CausalEdgeResult]:
        """Run VARLiNGAM causal discovery on the panel data.

        Args:
            df: Panel DataFrame with columns matching VARIABLES.
            region_id: Neo4j region ID for tagging results.

        Returns:
            List of CausalEdgeResult with valid edges.
        """
        # Validate input
        available_vars = [v for v in self.VARIABLES if v in df.columns]
        if len(available_vars) < 2:
            logger.warning("Need at least 2 variables for VARLiNGAM, got %d", len(available_vars))
            return []

        if len(df) < 52:
            logger.warning("Insufficient rows for VARLiNGAM: %d (need 52)", len(df))
            return []

        # Drop NaN rows in the variables we use
        data = df[available_vars].dropna()
        if len(data) < 52:
            logger.warning("After dropping NaN, insufficient rows: %d", len(data))
            return []

        try:
            # Import lingam here to avoid import errors if not installed
            import lingam
            from lingam import VARLiNGAM as LingamVARLiNGAM

            # Fit VARLiNGAM
            model = LingamVARLiNGAM(lags=self.MAX_LAGS, random_state=42)
            model.fit(data.values)

            # Extract adjacency matrices
            # adjacency_matrices_[l][i][j] = causal effect of var j on var i at lag l+1
            adj_matrices = model.adjacency_matrices_

            # Collect candidate edges
            candidates = []
            n_vars = len(available_vars)

            for lag in range(self.MAX_LAGS):
                adj = adj_matrices[lag]  # shape: (n_vars, n_vars)
                for target_idx in range(n_vars):
                    for source_idx in range(n_vars):
                        weight = adj[target_idx, source_idx]
                        if abs(weight) < self.MIN_WEIGHT:
                            continue

                        candidates.append({
                            "source": available_vars[source_idx],
                            "target": available_vars[target_idx],
                            "weight": float(weight),
                            "lag": lag + 1,
                        })

            if not candidates:
                logger.info("No candidate edges found for region %s (all below MIN_WEIGHT=%.2f)", region_id, self.MIN_WEIGHT)
                return []

            # Bootstrap p-values
            logger.info("Computing bootstrap p-values for %d candidate edges in %s...", len(candidates), region_id)
            p_values = self._bootstrap_p_values(data.values, available_vars, candidates)

            # Filter by p-value and create results
            results = []
            for cand, p_val in zip(candidates, p_values):
                if p_val > self.MAX_P_VALUE:
                    continue

                results.append(CausalEdgeResult(
                    source_variable=cand["source"],
                    target_variable=cand["target"],
                    weight=cand["weight"],
                    lag_weeks=cand["lag"],
                    p_value=round(p_val, 4),
                    region_id=region_id,
                ))

            logger.info(
                "VARLiNGAM discovered %d causal edges for %s (from %d candidates)",
                len(results), region_id, len(candidates),
            )
            return results

        except ImportError:
            logger.error("lingam package not installed. Install with: pip install lingam")
            return []
        except Exception as exc:
            logger.error("VARLiNGAM discovery failed for region %s: %s", region_id, exc)
            return []

    def _bootstrap_p_values(
        self,
        data: np.ndarray,
        var_names: List[str],
        candidates: List[dict],
    ) -> List[float]:
        """Compute approximate p-values via bootstrap resampling.

        For each candidate edge, p_value = fraction of bootstrap samples
        where |weight| < MIN_WEIGHT.
        """
        import lingam
        from lingam import VARLiNGAM as LingamVARLiNGAM

        n_samples = len(data)
        n_candidates = len(candidates)
        n_bootstrap = min(self.N_BOOTSTRAP, n_samples - 1)

        # Count how many bootstraps have |weight| < MIN_WEIGHT for each candidate
        weak_counts = np.zeros(n_candidates, dtype=int)

        for b in range(n_bootstrap):
            try:
                # Resample with replacement
                indices = np.random.choice(n_samples, size=n_samples, replace=True)
                boot_data = data[indices]

                # Fit VARLiNGAM on bootstrap sample
                boot_model = LingamVARLiNGAM(lags=self.MAX_LAGS, random_state=42 + b)
                boot_model.fit(boot_data)
                boot_adj = boot_model.adjacency_matrices_

                # Check each candidate edge
                for i, cand in enumerate(candidates):
                    lag_idx = cand["lag"] - 1
                    target_idx = var_names.index(cand["target"])
                    source_idx = var_names.index(cand["source"])

                    if lag_idx < len(boot_adj):
                        boot_weight = boot_adj[lag_idx][target_idx, source_idx]
                        if abs(boot_weight) < self.MIN_WEIGHT:
                            weak_counts[i] += 1
            except Exception:
                # Skip failed bootstrap samples
                continue

        # Convert to p-values
        effective_n = max(1, n_bootstrap)
        p_values = [count / effective_n for count in weak_counts]
        return p_values