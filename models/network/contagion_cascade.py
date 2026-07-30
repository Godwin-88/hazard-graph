"""
M11 — SIR Contagion Cascade Simulator
SIR-inspired contagion model on IGAD region graph.
Models how a food crisis in one region spreads to neighbours
via trade disruption, displacement flows, and market integration.

Maps to GraphAlpha:
  β (transmission) ≡ jump intensity λ_p in CIR+Jump model
  P(S→C) ≡ default probability in credit contagion literature
  Cascade probability ≡ CVaR at network level
"""

import numpy as np
from dataclasses import dataclass
from datetime import datetime

# Approximate populations (millions)
REGION_POPULATIONS = {
    'ethiopia': 120.0, 'kenya': 54.0, 'somalia': 17.0,
    'sudan': 46.0, 'south_sudan': 11.0, 'uganda': 47.0,
    'djibouti': 1.0, 'eritrea': 3.5, 'tanzania': 63.0,
    'burundi': 12.0, 'rwanda': 14.0
}

REGIONS = list(REGION_POPULATIONS.keys())

# Adjacency matrix: (source, target) → edge weight
# Weights represent trade + migration + market integration strength
ADJACENCY = {
    ('ethiopia', 'kenya'): 0.7,
    ('ethiopia', 'somalia'): 0.6,
    ('ethiopia', 'sudan'): 0.5,
    ('ethiopia', 'south_sudan'): 0.4,
    ('ethiopia', 'djibouti'): 0.8,
    ('ethiopia', 'eritrea'): 0.6,
    ('kenya', 'somalia'): 0.5,
    ('kenya', 'uganda'): 0.7,
    ('kenya', 'tanzania'): 0.6,
    ('kenya', 'ethiopia'): 0.7,
    ('somalia', 'ethiopia'): 0.6,
    ('somalia', 'kenya'): 0.5,
    ('somalia', 'djibouti'): 0.4,
    ('sudan', 'south_sudan'): 0.9,
    ('sudan', 'ethiopia'): 0.5,
    ('sudan', 'eritrea'): 0.4,
    ('south_sudan', 'uganda'): 0.6,
    ('south_sudan', 'ethiopia'): 0.4,
    ('south_sudan', 'sudan'): 0.9,
    ('uganda', 'kenya'): 0.7,
    ('uganda', 'south_sudan'): 0.6,
    ('uganda', 'rwanda'): 0.5,
    ('uganda', 'tanzania'): 0.4,
    ('tanzania', 'kenya'): 0.6,
    ('tanzania', 'uganda'): 0.4,
    ('tanzania', 'rwanda'): 0.3,
    ('tanzania', 'burundi'): 0.3,
    ('rwanda', 'uganda'): 0.5,
    ('rwanda', 'burundi'): 0.7,
    ('rwanda', 'tanzania'): 0.3,
    ('burundi', 'rwanda'): 0.7,
    ('burundi', 'tanzania'): 0.3,
    ('djibouti', 'ethiopia'): 0.8,
    ('djibouti', 'somalia'): 0.4,
    ('eritrea', 'ethiopia'): 0.6,
    ('eritrea', 'sudan'): 0.4,
}


@dataclass
class CascadeResult:
    source_region: str
    horizon_weeks: int
    cascade_probabilities: dict[str, float]
    critical_intervention_node: str
    expected_affected_population: float
    simulation_paths: int
    simulated_at: str


class SIRCascadeSimulator:
    """
    States: Susceptible (S=0), At-Risk (A=1), Crisis (C=2), Recovering (R=3)
    Transition probabilities calibrated from historical IPC cascade sequences.
    """
    REGIONS = REGIONS

    # Transmission parameters calibrated from FEWS NET historical cascades
    BETA = 0.18  # S → A transmission rate (per week, per infected neighbour)
    GAMMA = 0.25  # A → C escalation rate
    DELTA = 0.08  # C → R recovery rate (slow — aid takes time)

    def __init__(self):
        self._build_neighbour_cache()

    def _build_neighbour_cache(self):
        """Pre-compute neighbour lists for vectorised simulation."""
        self.neighbours: dict[str, list[tuple[str, float]]] = {
            r: [] for r in self.REGIONS
        }
        for (src, tgt), weight in ADJACENCY.items():
            self.neighbours[src].append((tgt, weight))
            self.neighbours[tgt].append((src, weight))

    def simulate(
        self,
        initial_states: dict[str, int],
        risk_scores: dict[str, float],
        vulnerability_multipliers: dict[str, float],
        n_paths: int = 1000,
        horizon_weeks: int = 8
    ) -> dict[str, np.ndarray]:
        """
        Monte Carlo SIR cascade.
        Returns {region: array of shape (n_paths,)} — final state per path.
        Vectorised where possible for performance.
        """
        rng = np.random.default_rng(42)
        n_regions = len(self.REGIONS)
        region_idx = {r: i for i, r in enumerate(self.REGIONS)}

        # Pre-allocate arrays
        states = np.zeros((n_paths, n_regions), dtype=np.int8)
        for r, s in initial_states.items():
            if r in region_idx:
                states[:, region_idx[r]] = s

        # Pre-compute neighbour indices
        nb_indices = []
        nb_weights = []
        for r in self.REGIONS:
            idxs = [region_idx[nb] for nb, _ in self.neighbours[r]]
            wts = [w for _, w in self.neighbours[r]]
            nb_indices.append(idxs)
            nb_weights.append(wts)

        risk_arr = np.array([risk_scores.get(r, 50.0) for r in self.REGIONS])
        vuln_arr = np.array([vulnerability_multipliers.get(r, 1.5) for r in self.REGIONS])

        for week in range(horizon_weeks):
            new_states = states.copy()

            for i, region in enumerate(self.REGIONS):
                s_arr = states[:, i]
                nb_idx = nb_indices[i]
                nb_wt = nb_weights[i]

                # Susceptible → At-Risk
                mask_s = s_arr == 0
                if mask_s.any() and nb_idx:
                    # Count infected neighbours (state >= 1) weighted by edge weight
                    infected_counts = np.zeros(n_paths)
                    for nb_i, w in zip(nb_idx, nb_wt):
                        infected_counts += (states[:, nb_i] >= 1).astype(float) * w
                    p_sa = np.minimum(0.95,
                                      self.BETA * infected_counts * vuln_arr[i] * (1 + risk_arr[i] / 100))
                    new_states[mask_s & (rng.random(n_paths) < p_sa), i] = 1

                # At-Risk → Crisis
                mask_a = s_arr == 1
                if mask_a.any():
                    p_ac = np.minimum(0.95,
                                      self.GAMMA * vuln_arr[i] * (risk_arr[i] / 100) *
                                      (1 + 0.5 * risk_arr[i] / 100))
                    new_states[mask_a & (rng.random(n_paths) < p_ac), i] = 2

                # Crisis → Recovering
                mask_c = s_arr == 2
                if mask_c.any():
                    new_states[mask_c & (rng.random(n_paths) < self.DELTA), i] = 3

            states = new_states

        return {r: states[:, region_idx[r]] for r in self.REGIONS}

    def compute_cascade_result(
        self,
        source_region: str,
        risk_scores: dict[str, float],
        vulnerability_multipliers: dict[str, float],
        n_paths: int = 1000,
        horizon_weeks: int = 8
    ) -> CascadeResult:
        """
        Run cascade with source_region in Crisis state initially.
        Returns full CascadeResult with intervention recommendation.
        """
        initial_states = {r: 0 for r in self.REGIONS}
        initial_states[source_region] = 2  # source starts in Crisis

        final_states = self.simulate(
            initial_states, risk_scores,
            vulnerability_multipliers, n_paths, horizon_weeks
        )

        # P(enters Crisis) = fraction of paths where final state >= 2
        cascade_probs = {
            r: float(np.mean(final_states[r] >= 2))
            for r in self.REGIONS
        }

        # Expected affected population (millions)
        expected_pop = sum(
            cascade_probs[r] * REGION_POPULATIONS.get(r, 0)
            for r in self.REGIONS
        )

        # Critical intervention node: removing which region
        # most reduces total cascade probability
        best_node = source_region
        best_reduction = 0.0
        for candidate in self.neighbours[source_region]:
            nb_region, _ = candidate
            # Simulate with candidate treated (risk reduced by 50%)
            modified_risk = dict(risk_scores)
            modified_risk[nb_region] = risk_scores.get(nb_region, 50) * 0.5
            modified_final = self.simulate(
                initial_states, modified_risk,
                vulnerability_multipliers, n_paths // 2, horizon_weeks
            )
            reduction = sum(
                cascade_probs[r] - float(np.mean(modified_final[r] >= 2))
                for r in self.REGIONS
            )
            if reduction > best_reduction:
                best_reduction = reduction
                best_node = nb_region

        return CascadeResult(
            source_region=source_region,
            horizon_weeks=horizon_weeks,
            cascade_probabilities=cascade_probs,
            critical_intervention_node=best_node,
            expected_affected_population=expected_pop,
            simulation_paths=n_paths,
            simulated_at=datetime.utcnow().isoformat()
        )

    async def run_top3(
        self,
        risk_scores: dict[str, float],
        vulnerability_multipliers: dict[str, float],
        neo4j_session
    ) -> list[CascadeResult]:
        """Run cascade for top-3 highest risk regions."""
        sorted_regions = sorted(
            risk_scores.keys(), key=lambda r: risk_scores.get(r, 0), reverse=True
        )
        top3 = sorted_regions[:3]
        results = []
        for source in top3:
            result = self.compute_cascade_result(
                source, risk_scores, vulnerability_multipliers
            )
            results.append(result)
            await self.write_to_neo4j(result, neo4j_session)
        return results

    async def write_to_neo4j(
        self, result: CascadeResult, neo4j_session
    ) -> None:
        await neo4j_session.run(
            'MERGE (c:CascadeSignal {id: $id}) '
            'SET c.source_region = $src, '
            '    c.cascade_probs_json = $probs, '
            '    c.critical_node = $crit, '
            '    c.expected_pop_millions = $pop, '
            '    c.simulated_at = $sat',
            id=f'cascade_{result.source_region}_{result.simulated_at[:10]}',
            src=result.source_region,
            probs=str(result.cascade_probabilities),
            crit=result.critical_intervention_node,
            pop=result.expected_affected_population,
            sat=result.simulated_at
        )