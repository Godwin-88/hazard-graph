"""
PPO (Proximal Policy Optimisation) training loop.
Shares the same REINFORCE principle as cautious-disco's policy
gradient but with clipped objective and value function baseline.

PPO objective:
  L_CLIP = E[min(r_t × A_t, clip(r_t, 1-ε, 1+ε) × A_t)]
where:
  r_t = π(a|s) / π_old(a|s)  (probability ratio)
  A_t = R_t - V(s_t)         (advantage estimate)
  ε   = 0.2                  (clip epsilon)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import os
from collections import deque
from models.rl.gnn_policy import GNNPolicyNetwork
from models.rl.alert_env import HazardAlertEnv


class PPOBuffer:
    """Rollout buffer storing (state, action, reward, value, log_prob)."""

    def __init__(self, size: int = 2048):
        self.size = size
        self.clear()

    def clear(self):
        self.node_features = []
        self.edge_indices = []
        self.edge_weights = []
        self.actions = []
        self.rewards = []
        self.values = []
        self.log_probs = []
        self.dones = []
        self.ptr = 0

    def add(self, state, actions, reward, value, log_probs, done):
        self.node_features.append(state.node_features)
        self.edge_indices.append(state.edge_index)
        self.edge_weights.append(state.edge_weights)
        self.actions.append(actions)
        self.rewards.append(reward)
        self.values.append(value)
        self.log_probs.append(log_probs)
        self.dones.append(done)
        self.ptr += 1

    def compute_returns(self, gamma: float = 0.99, lam: float = 0.95) -> list[float]:
        """GAE (Generalised Advantage Estimation) returns."""
        returns = []
        gae = 0.0
        vals = self.values + [0.0]
        for t in reversed(range(len(self.rewards))):
            delta = (self.rewards[t] + gamma * vals[t + 1] *
                     (1 - self.dones[t]) - vals[t])
            gae = delta + gamma * lam * (1 - self.dones[t]) * gae
            returns.insert(0, gae + vals[t])
        return returns


class PPOTrainer:
    CLIP_EPS = 0.2
    VF_COEF = 0.5
    ENT_COEF = 0.01  # entropy bonus — prevents premature convergence
    LR = 3e-4
    EPOCHS = 4  # PPO update epochs per rollout
    BATCH_SIZE = 64
    SAVE_DIR = 'models/saved'

    def __init__(self):
        self.policy = GNNPolicyNetwork()
        self.optimiser = torch.optim.Adam(
            self.policy.parameters(), lr=self.LR
        )
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimiser, T_max=200, eta_min=1e-5
        )
        self.buffer = PPOBuffer()
        self.env = HazardAlertEnv()
        self.rewards_history: deque = deque(maxlen=100)
        self.is_trained = False

    def collect_rollout(self, n_steps: int = 512):
        """Collect rollout data from environment."""
        self.buffer.clear()
        obs, _ = self.env.reset()
        episode_reward = 0.0

        for step in range(n_steps):
            graph_state = self.env.get_graph_state()
            with torch.no_grad():
                actions, log_probs, value = self.policy.act(graph_state)

            action_np = actions.numpy()
            obs, reward, terminated, truncated, info = self.env.step(action_np)
            episode_reward += reward
            done = terminated or truncated

            self.buffer.add(
                graph_state, actions, reward,
                value.item(), log_probs, float(done)
            )
            if done:
                self.rewards_history.append(episode_reward)
                episode_reward = 0.0
                obs, _ = self.env.reset()

    def update(self):
        """PPO policy update from collected rollout."""
        returns = self.buffer.compute_returns()
        returns_t = torch.FloatTensor(returns)

        # Normalise advantages
        values_t = torch.FloatTensor(self.buffer.values)
        advantages = returns_t - values_t
        advantages = (advantages - advantages.mean()) / \
                     (advantages.std() + 1e-8)

        total_loss = 0.0
        for epoch in range(self.EPOCHS):
            idx = np.random.permutation(len(self.buffer.rewards))
            for start in range(0, len(idx), self.BATCH_SIZE):
                batch = idx[start:start + self.BATCH_SIZE]

                for b_idx in batch:
                    nf = self.buffer.node_features[b_idx]
                    ei = self.buffer.edge_indices[b_idx]
                    ew = self.buffer.edge_weights[b_idx]
                    logits, value = self.policy(nf, ei, ew)
                    dist = torch.distributions.Categorical(logits=logits)
                    new_log_probs = dist.log_prob(self.buffer.actions[b_idx])
                    entropy = dist.entropy().mean()

                    # PPO clipped objective
                    ratio = torch.exp(new_log_probs - self.buffer.log_probs[b_idx])
                    adv_b = advantages[b_idx].unsqueeze(-1).expand_as(ratio)
                    surr1 = ratio * adv_b
                    surr2 = torch.clamp(ratio, 1 - self.CLIP_EPS,
                                        1 + self.CLIP_EPS) * adv_b
                    policy_loss = -torch.min(surr1, surr2).mean()

                    # Value function loss
                    value_loss = F.mse_loss(
                        value.squeeze(), returns_t[b_idx].mean()
                    )

                    loss = (policy_loss +
                            self.VF_COEF * value_loss -
                            self.ENT_COEF * entropy)

                    self.optimiser.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(
                        self.policy.parameters(), 0.5
                    )
                    self.optimiser.step()
                    total_loss += loss.item()

        self.scheduler.step()
        return total_loss

    def train(self, n_iterations: int = 100, rollout_steps: int = 256,
              verbose: bool = True):
        """
        Full PPO training loop.
        100 iterations × 256 steps = 25,600 environment interactions.
        ~3-5 minutes on CPU.
        """
        os.makedirs(self.SAVE_DIR, exist_ok=True)

        for iteration in range(n_iterations):
            self.collect_rollout(rollout_steps)
            loss = self.update()

            if verbose and iteration % 10 == 0:
                avg_reward = (np.mean(self.rewards_history)
                              if self.rewards_history else 0.0)
                print(f"Iter {iteration:3d} | "
                      f"Loss: {loss:.4f} | "
                      f"Avg Reward: {avg_reward:.2f} | "
                      f"LR: {self.scheduler.get_last_lr()[0]:.6f}")

        self.is_trained = True
        torch.save({
            'policy_state': self.policy.state_dict(),
            'optimiser': self.optimiser.state_dict(),
            'rewards': list(self.rewards_history),
        }, f'{self.SAVE_DIR}/ppo_alert_policy.pt')

    def load(self) -> bool:
        path = f'{self.SAVE_DIR}/ppo_alert_policy.pt'
        if not os.path.exists(path):
            return False
        checkpoint = torch.load(path, map_location='cpu')
        self.policy.load_state_dict(checkpoint['policy_state'])
        self.policy.eval()
        self.is_trained = True
        return True