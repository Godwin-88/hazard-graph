"""
Gymnasium-compatible environment for HazardGraph DRL training.
Uses synthetic episode data derived from historical ICPAC patterns.
Episode: 12 weeks (one seasonal cycle), Step: 1 week.
"""

import gymnasium as gym
import numpy as np
import torch
from gymnasium import spaces
from models.rl.graph_state import GraphState, REGIONS, N_FEATURES, N_ACTIONS
from models.rl.reward_calculator import compute_reward

N_REGIONS = len(REGIONS)


class HazardAlertEnv(gym.Env):
    """
    Episode: 12 weeks (one seasonal cycle)
    Step:    1 week
    State:   GraphState (11 nodes × 10 features + causal edges)
    Action:  Multi-discrete (11 regions × 4 alert levels)
    Reward:  Composite reward balancing IPC improvement vs fatigue
    """
    metadata = {'render_modes': ['human']}

    def __init__(self, seed: int = 42):
        super().__init__()
        self.seed_val = seed
        self.rng = np.random.default_rng(seed)
        self.current_step = 0
        self.MAX_STEPS = 12

        # Observation: flattened node features
        self.observation_space = spaces.Box(
            low=-3.0, high=3.0,
            shape=(N_REGIONS * N_FEATURES,),
            dtype=np.float32
        )
        # Action: discrete level per region
        self.action_space = spaces.MultiDiscrete(
            [N_ACTIONS] * N_REGIONS
        )
        self.state_data = None
        self._reset_state()

    def _reset_state(self) -> None:
        """Generate a new synthetic episode."""
        self.ipc_phases = {
            r: float(self.rng.choice([1, 2, 3, 4], p=[0.35, 0.35, 0.20, 0.10]))
            for r in REGIONS
        }
        self.spi_values = {
            r: float(self.rng.normal(0, 1.0)) for r in REGIONS
        }
        self.risk_scores = {
            r: float(np.clip(
                (self.ipc_phases[r] - 1) / 4 * 70 + self.rng.normal(0, 10),
                0, 100
            )) for r in REGIONS
        }
        self.weeks_since_alert = {r: 10 for r in REGIONS}
        self.response_rates = {
            r: float(self.rng.uniform(0.3, 0.8)) for r in REGIONS
        }
        self.alert_history = {r: 0 for r in REGIONS}
        # Synthetic causal edges
        self.causal_edges = self._generate_causal_edges()

    def _generate_causal_edges(self) -> list:
        """Generate realistic causal edges for episode."""
        from models.network.contagion_cascade import ADJACENCY
        edges = []
        for (src, tgt), w in ADJACENCY.items():
            if self.rng.random() < 0.7:
                edges.append((src, tgt, w * self.rng.uniform(0.5, 1.5)))
        return edges

    def _get_observation(self) -> np.ndarray:
        """Build flattened node features."""
        features = np.zeros((N_REGIONS, N_FEATURES), dtype=np.float32)
        for i, region in enumerate(REGIONS):
            features[i] = [
                self.risk_scores[region] / 100.0,
                (self.ipc_phases[region] - 1) / 4.0,
                max(0, -self.spi_values[region]) / 3.0,
                max(0, self.spi_values[region]) / 3.0,
                self.risk_scores[region] / 100.0 * 0.9,
                self.risk_scores[region] / 100.0 * 0.85,
                0.1,
                1.5 / 2.5,
                min(self.weeks_since_alert[region], 12) / 12.0,
                self.response_rates[region],
            ]
        return features.flatten()

    def get_graph_state(self) -> GraphState:
        """Build full GraphState for GNN policy."""
        features = self._get_observation().reshape(N_REGIONS, N_FEATURES)
        region_idx = {r: i for i, r in enumerate(REGIONS)}
        edges_src, edges_tgt, edge_w = [], [], []
        for src, tgt, w in self.causal_edges:
            if src in region_idx and tgt in region_idx:
                edges_src.append(region_idx[src])
                edges_tgt.append(region_idx[tgt])
                edge_w.append(w)
        if not edges_src:
            for i in range(N_REGIONS):
                edges_src.append(i)
                edges_tgt.append(i)
                edge_w.append(1.0)
        return GraphState(
            node_features=torch.FloatTensor(features),
            edge_index=torch.LongTensor([edges_src, edges_tgt]),
            edge_weights=torch.FloatTensor(edge_w)
        )

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict]:
        """
        Execute one week:
        1. Apply actions (generate alerts)
        2. Evolve state (SIR-like dynamics)
        3. Compute reward
        """
        prev_ipc = dict(self.ipc_phases)

        # Update alert tracking
        for i, region in enumerate(REGIONS):
            if action[i] > 0:
                self.weeks_since_alert[region] = 0
                self.alert_history[region] += 1
            else:
                self.weeks_since_alert[region] += 1

        # Evolve environment (simplified SIR-like dynamics)
        for region in REGIONS:
            spi = self.spi_values[region]
            ipc = self.ipc_phases[region]
            alert = action[REGIONS.index(region)]

            # SPI drifts (climate dynamics)
            self.spi_values[region] += float(self.rng.normal(-0.05, 0.3))
            self.spi_values[region] = float(np.clip(self.spi_values[region], -3, 3))

            # IPC evolves based on SPI and alert
            if spi < -1.5 and alert == 0:
                self.ipc_phases[region] = min(5, ipc + self.rng.choice([0, 1]))
            elif alert >= 2 and self.response_rates[region] > 0.5:
                self.ipc_phases[region] = max(1, ipc + self.rng.choice([-1, 0]))
            else:
                self.ipc_phases[region] = float(
                    np.clip(ipc + self.rng.normal(0, 0.3), 1, 5)
                )

            self.risk_scores[region] = float(np.clip(
                (self.ipc_phases[region] - 1) / 4 * 80 +
                (-self.spi_values[region]) * 10, 0, 100
            ))

        reward, components = compute_reward(
            actions=action.tolist(),
            regions=REGIONS,
            current_ipc=self.ipc_phases,
            prev_ipc=prev_ipc,
            response_rates=self.response_rates,
            weeks_since_alert=self.weeks_since_alert,
            risk_scores=self.risk_scores
        )

        self.current_step += 1
        terminated = self.current_step >= self.MAX_STEPS
        obs = self._get_observation()

        return obs, reward, terminated, False, {
            'reward_components': components,
            'ipc_phases': dict(self.ipc_phases),
            'risk_scores': dict(self.risk_scores)
        }

    def reset(self, *, seed=None, options=None) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.current_step = 0
        self._reset_state()
        return self._get_observation(), {}