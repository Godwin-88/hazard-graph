"""HazardGraph — CIR + Jump Diffusion SDE for rainfall probability.

dR(t) = kappa * (theta - R(t)) * dt + sigma * sqrt(|R(t)|) * dW(t)
        + J * dN(t)

Parameters calibrated via MLE on historical SPI series.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np

from db.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

COUNTRY_PARAMS: dict[str, dict] = {
    "ethiopia": {
        "kappa": 2.1, "theta": 0.0, "sigma": 0.8,
        "jump_intensity": 0.15, "jump_mean": 1.2,
    },
    "kenya": {
        "kappa": 1.8, "theta": 0.0, "sigma": 0.9,
        "jump_intensity": 0.18, "jump_mean": 1.4,
    },
    "somalia": {
        "kappa": 2.5, "theta": 0.0, "sigma": 1.1,
        "jump_intensity": 0.22, "jump_mean": 1.8,
    },
    "sudan": {
        "kappa": 2.8, "theta": 0.0, "sigma": 1.0,
        "jump_intensity": 0.20, "jump_mean": 1.5,
    },
    "south_sudan": {
        "kappa": 2.0, "theta": 0.0, "sigma": 0.9,
        "jump_intensity": 0.17, "jump_mean": 1.3,
    },
    "uganda": {
        "kappa": 1.6, "theta": 0.0, "sigma": 0.7,
        "jump_intensity": 0.12, "jump_mean": 1.1,
    },
    "djibouti": {
        "kappa": 3.0, "theta": 0.0, "sigma": 1.3,
        "jump_intensity": 0.25, "jump_mean": 2.0,
    },
    "eritrea": {
        "kappa": 2.7, "theta": 0.0, "sigma": 1.2,
        "jump_intensity": 0.21, "jump_mean": 1.6,
    },
    "tanzania": {
        "kappa": 1.7, "theta": 0.0, "sigma": 0.75,
        "jump_intensity": 0.13, "jump_mean": 1.2,
    },
    "burundi": {
        "kappa": 1.5, "theta": 0.0, "sigma": 0.65,
        "jump_intensity": 0.10, "jump_mean": 1.0,
    },
    "rwanda": {
        "kappa": 1.5, "theta": 0.0, "sigma": 0.60,
        "jump_intensity": 0.09, "jump_mean": 0.9,
    },
}


class RainfallSDE:
    """CIR + Jump Diffusion SDE for rainfall probability simulation."""

    COUNTRY_PARAMS = COUNTRY_PARAMS

    def simulate(
        self,
        country: str,
        r0: float,
        n_paths: int = 5000,
        n_steps: int = 4,
        dt: float = 1 / 52,
    ) -> dict[str, Any]:
        """Vectorised Monte Carlo simulation using numpy.

        Args:
            country: IGAD country identifier.
            r0: Current SPI value (initial condition).
            n_paths: Number of Monte Carlo paths.
            n_steps: Number of weekly steps (4-week horizon).
            dt: Weekly time step.

        Returns:
            Dict with p_flood_4w, p_drought_4w, p_severe_4w,
            current_vol, jump_intensity.
        """
        params = COUNTRY_PARAMS.get(country, COUNTRY_PARAMS["kenya"])
        R = np.full((n_paths,), r0)
        rng = np.random.default_rng(42)

        for _ in range(n_steps):
            dW = rng.standard_normal(n_paths) * np.sqrt(dt)
            drift = params["kappa"] * (params["theta"] - R) * dt
            diffusion = params["sigma"] * np.sqrt(np.abs(R)) * dW
            n_jumps = rng.poisson(params["jump_intensity"] * dt, n_paths)
            jumps = n_jumps * rng.exponential(params["jump_mean"], n_paths)
            jump_sign = rng.choice([-1, 1], n_paths, p=[0.65, 0.35])
            R = R + drift + diffusion + jumps * jump_sign

        return {
            "p_flood_4w": float(np.mean(R > 1.5)),
            "p_drought_4w": float(np.mean(R < -1.0)),
            "p_severe_4w": float(np.mean(R < -1.5)),
            "current_vol": float(params["sigma"] * np.sqrt(abs(r0))),
            "jump_intensity": params["jump_intensity"],
        }

    async def run_all_regions(self, neo4j_session) -> dict[str, dict]:
        """Run SDE simulation for every Region in Neo4j.

        For each region:
          1. Fetch most recent RainfallSignal.spi_30d_smoothed
          2. Run simulate(country, r0=spi)
          3. Write StochasticSignal node to Neo4j
          4. Return {region_id: simulation_result} for all regions
        """
        regions_query = """
        MATCH (r:Region)
        RETURN r.id AS region_id, r.name AS name, r.country AS country
        ORDER BY r.name
        """
        regions = await neo4j_client.execute_read(regions_query)
        results: dict[str, dict] = {}

        for region in regions:
            region_id = region["region_id"]
            country = region.get("country", "").lower().replace(" ", "_")

            spi_query = """
            MATCH (r:Region {id: $region_id})
            MATCH (r)-[:HAS_SIGNAL]->(s:RainfallSignal)
            RETURN s.spi_30d_smoothed AS spi
            ORDER BY s.created_at DESC
            LIMIT 1
            """
            spi_result = await neo4j_client.execute_read(spi_query, {"region_id": region_id})
            spi = spi_result[0]["spi"] if spi_result else 0.0

            sim = self.simulate(country if country else "kenya", r0=spi)
            sim["region_id"] = region_id

            now = datetime.now(timezone.utc).isoformat()
            signal_id = f"stochastic_{region_id}"

            write_query = """
            MERGE (s:StochasticSignal {id: $id})
            SET s.model = 'CIR_JumpDiffusion',
                s.p_flood_4w = $p_flood,
                s.p_drought_4w = $p_drought,
                s.p_severe_4w = $p_severe,
                s.current_vol = $vol,
                s.jump_intensity = $ji,
                s.region_id = $region_id,
                s.created_at = $now
            """
            await neo4j_client.execute_write(write_query, {
                "id": signal_id,
                "p_flood": sim["p_flood_4w"],
                "p_drought": sim["p_drought_4w"],
                "p_severe": sim["p_severe_4w"],
                "vol": sim["current_vol"],
                "ji": sim["jump_intensity"],
                "region_id": region_id,
                "now": now,
            })

            results[region_id] = sim
            logger.info(
                "SDE simulation for %s (country=%s): p_flood=%.3f p_drought=%.3f p_severe=%.3f",
                region_id, country, sim["p_flood_4w"], sim["p_drought_4w"], sim["p_severe_4w"],
            )

        return results