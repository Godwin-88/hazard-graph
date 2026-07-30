"""
Production inference: load trained PPO policy + GNN, generate
optimal alert actions from live pipeline state.
"""

import torch
from models.rl.gnn_policy import GNNPolicyNetwork
from models.rl.graph_state import GraphState, REGIONS
from models.rl.ppo_trainer import PPOTrainer
from dataclasses import dataclass

ACTION_LABELS = {
    0: 'NO_ALERT',
    1: 'LOW_ADVISORY',
    2: 'MEDIUM_SMS',
    3: 'HIGH_ESCALATE'
}


@dataclass
class PolicyRecommendation:
    region_id: str
    action: int
    action_label: str
    action_probability: float
    reasoning: str


class AlertPolicyInference:

    def __init__(self):
        self.trainer = PPOTrainer()
        self._ensure_model_loaded()

    def _ensure_model_loaded(self):
        if not self.trainer.load():
            print("No saved PPO model — training on synthetic data...")
            self.trainer.train(n_iterations=50, verbose=False)

    def recommend(
        self, state: GraphState
    ) -> list[PolicyRecommendation]:
        """
        Run trained GNN policy on current graph state.
        Returns list of PolicyRecommendation, one per region.
        """
        self.trainer.policy.eval()
        with torch.no_grad():
            logits, value = self.trainer.policy(
                state.node_features,
                state.edge_index,
                state.edge_weights
            )
            probs = torch.softmax(logits, dim=-1)
            actions = logits.argmax(dim=-1)

        recommendations = []
        for i, region in enumerate(REGIONS):
            action = int(actions[i].item())
            action_prob = float(probs[i, action].item())
            node_risk = float(state.node_features[i, 0].item())
            weeks_since = float(state.node_features[i, 8].item()) * 12

            if action == 0:
                reason = (
                    f"Risk level {node_risk * 100:.0f}% — below alert threshold"
                    if node_risk < 0.6
                    else f"Alert fatigue: {weeks_since:.0f}w since last alert"
                )
            elif action == 1:
                reason = f"Emerging risk {node_risk * 100:.0f}% — advisory recommended"
            elif action == 2:
                reason = f"Elevated risk {node_risk * 100:.0f}% — SMS dispatch recommended"
            else:
                reason = (f"Critical risk {node_risk * 100:.0f}% — "
                          f"immediate escalation to government required")

            recommendations.append(PolicyRecommendation(
                region_id=region,
                action=action,
                action_label=ACTION_LABELS[action],
                action_probability=action_prob,
                reasoning=reason
            ))

        return sorted(recommendations, key=lambda r: r.action, reverse=True)