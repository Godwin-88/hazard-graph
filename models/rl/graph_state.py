"""
Graph state representation for the DRL agent.
State: Graph-structured — 11 region nodes × 10 features each
       + VARLiNGAM causal edges as graph connectivity
"""

import numpy as np
import torch
from dataclasses import dataclass

NODE_FEATURES = [
    'bma_posterior',             # 0: BMA risk probability
    'hmm_regime_encoded',        # 1: 0-4 regime level
    'sde_p_drought',             # 2: SDE drought probability
    'sde_p_flood',               # 3: SDE flood probability
    'lstm_p_crisis',             # 4: LSTM crisis probability
    'xgb_p_crisis',              # 5: XGBoost crisis probability
    'pagerank_score',            # 6: contagion centrality
    'vulnerability_multiplier',  # 7: composite vulnerability
    'weeks_since_last_alert',    # 8: alert fatigue indicator
    'last_response_rate',        # 9: community engagement
]
N_FEATURES = len(NODE_FEATURES)  # 10
N_REGIONS = 11
REGIONS = [
    'kenya', 'ethiopia', 'somalia', 'sudan', 'south_sudan',
    'uganda', 'djibouti', 'eritrea', 'tanzania', 'burundi', 'rwanda'
]


@dataclass
class GraphState:
    """
    Full graph-structured state for DRL agent.
    node_features: (N_REGIONS, N_FEATURES) float32 tensor
    edge_index:    (2, E) long tensor — source + target node indices
    edge_weights:  (E,) float32 tensor — VARLiNGAM causal weights
    """
    node_features: torch.Tensor  # (11, 10)
    edge_index: torch.Tensor  # (2, E)
    edge_weights: torch.Tensor  # (E,)

    @classmethod
    def from_pipeline_outputs(
        cls,
        bma_results: dict,
        sde_results: dict,
        hmm_results: dict,
        lstm_results: dict,
        xgb_results: dict,
        pagerank_results: dict,
        vulnerability_multipliers: dict,
        alert_history: dict,
        response_rates: dict,
        causal_edges: list
    ) -> 'GraphState':
        """Build GraphState from pipeline outputs."""
        features = np.zeros((N_REGIONS, N_FEATURES), dtype=np.float32)

        REGIME_MAP = {
            'Baseline': 0.0, 'DroughtOnset': 0.25,
            'SevereDrought': 0.75, 'FloodWatch': 0.50,
            'FloodEmergency': 1.0
        }

        for i, region in enumerate(REGIONS):
            bma = bma_results.get(region)
            sde = sde_results.get(region, {})
            hmm = hmm_results.get(region, {})
            lstm = lstm_results.get(region)
            xgb = xgb_results.get(region)
            pr = pagerank_results.get(region)

            features[i] = [
                bma.posterior_risk if bma else 0.5,
                REGIME_MAP.get(hmm.get('regime', 'Baseline'), 0.0),
                sde.get('p_drought_4w', 0.1),
                sde.get('p_flood_4w', 0.1),
                max(lstm.probabilities[2:]) if lstm else 0.3,
                xgb.p_crisis if xgb else 0.3,
                pr.pagerank_score if pr else 0.1,
                min(vulnerability_multipliers.get(region, 1.5), 2.5) / 2.5,
                min(alert_history.get(region, 10), 12) / 12.0,
                response_rates.get(region, 0.5),
            ]

        # Build edge_index from causal edges
        region_idx = {r: i for i, r in enumerate(REGIONS)}
        edges_src, edges_tgt, edge_w = [], [], []
        for src, tgt, weight in causal_edges:
            if src in region_idx and tgt in region_idx:
                edges_src.append(region_idx[src])
                edges_tgt.append(region_idx[tgt])
                edge_w.append(float(weight))

        if not edges_src:
            # Self-loops as fallback to avoid empty edge_index
            for i in range(N_REGIONS):
                edges_src.append(i)
                edges_tgt.append(i)
                edge_w.append(1.0)

        return cls(
            node_features=torch.FloatTensor(features),
            edge_index=torch.LongTensor([edges_src, edges_tgt]),
            edge_weights=torch.FloatTensor(edge_w)
        )