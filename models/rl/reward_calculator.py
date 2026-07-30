"""
Reward function for the HazardAlert DRL environment.
Balances early warning effectiveness vs alert fatigue.

Key insight: too many alerts → communities ignore them → negative reward
Too few alerts → IPC worsens → heavy negative reward
Optimal: targeted alerts where response rate is high and risk is real
"""

import numpy as np
from dataclasses import dataclass


@dataclass
class RewardComponents:
    ipc_improvement: float
    response_rate_bonus: float
    fatigue_penalty: float
    missed_alert_penalty: float
    action_cost: float
    total: float


def compute_reward(
    actions: list[int],
    regions: list[str],
    current_ipc: dict[str, float],
    prev_ipc: dict[str, float],
    response_rates: dict[str, float],
    weeks_since_alert: dict[str, int],
    risk_scores: dict[str, float]
) -> tuple[float, RewardComponents]:
    """
    Composite reward:
      +5.0 per IPC phase improvement
      +2.0 per response rate bonus when alert sent
      -1.5 per fatigue penalty if alert sent < 2 weeks since last
      -4.0 per missed alert when IPC >= 3 and risk > 65%
      -0.3 per action level (operational cost)
    """
    ipc_improvement = 0.0
    response_bonus = 0.0
    fatigue_penalty = 0.0
    missed_penalty = 0.0
    action_cost = 0.0

    for i, region in enumerate(regions):
        action = actions[i]
        curr = current_ipc.get(region, 2.0)
        prev = prev_ipc.get(region, 2.0)
        resp = response_rates.get(region, 0.5)
        weeks = weeks_since_alert.get(region, 10)
        risk = risk_scores.get(region, 50.0) / 100.0

        # IPC improvement reward (observed 4 weeks later)
        delta_ipc = prev - curr  # positive if phase decreased
        ipc_improvement += 5.0 * delta_ipc

        if action > 0:
            # Response rate bonus (community engaged)
            response_bonus += 2.0 * resp * action

            # Fatigue penalty: alert too soon after last one
            if weeks < 2:
                fatigue_penalty -= 1.5 * (1.0 - weeks / 2.0)

            # Action cost (sending alerts has operational cost)
            action_cost -= 0.3 * action

        else:
            # Missed alert penalty: high risk ignored
            if risk > 0.65 and curr >= 3:
                missed_penalty -= 4.0 * risk

    total = (ipc_improvement + response_bonus +
             fatigue_penalty + missed_penalty + action_cost)

    components = RewardComponents(
        ipc_improvement=ipc_improvement,
        response_rate_bonus=response_bonus,
        fatigue_penalty=fatigue_penalty,
        missed_alert_penalty=missed_penalty,
        action_cost=action_cost,
        total=total
    )
    return total, components