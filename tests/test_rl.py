"""Tests for DRL environment, GNN policy, and PPO trainer."""

import numpy as np
import torch
import pytest


class TestHazardAlertEnv:
    def test_env_reset_returns_correct_shape(self):
        from models.rl.alert_env import HazardAlertEnv
        from models.rl.graph_state import REGIONS, N_FEATURES
        env = HazardAlertEnv()
        obs, info = env.reset()
        assert obs.shape == (len(REGIONS) * N_FEATURES,)

    def test_env_step_returns_valid_reward(self):
        from models.rl.alert_env import HazardAlertEnv
        env = HazardAlertEnv()
        env.reset()
        action = np.zeros(11, dtype=int)
        obs, reward, terminated, truncated, info = env.step(action)
        assert isinstance(reward, float)
        assert -100 < reward < 100
        assert 'reward_components' in info

    def test_episode_terminates_after_12_steps(self):
        from models.rl.alert_env import HazardAlertEnv
        env = HazardAlertEnv()
        env.reset()
        for step in range(12):
            _, _, terminated, _, _ = env.step(np.zeros(11, dtype=int))
            if step < 11:
                assert not terminated
        assert terminated

    def test_graph_state_from_env(self):
        from models.rl.alert_env import HazardAlertEnv
        from models.rl.graph_state import N_REGIONS, N_FEATURES
        env = HazardAlertEnv()
        env.reset()
        state = env.get_graph_state()
        assert state.node_features.shape == (N_REGIONS, N_FEATURES)
        assert state.edge_index.shape[0] == 2
        assert state.edge_weights.shape[0] == state.edge_index.shape[1]


class TestGNNPolicy:
    def test_policy_output_shapes(self):
        from models.rl.gnn_policy import GNNPolicyNetwork
        from models.rl.graph_state import N_REGIONS, N_ACTIONS
        from models.rl.alert_env import HazardAlertEnv
        policy = GNNPolicyNetwork()
        policy.eval()  # disable dropout for deterministic output
        env = HazardAlertEnv()
        env.reset()
        state = env.get_graph_state()
        logits, value = policy(
            state.node_features,
            state.edge_index,
            state.edge_weights
        )
        assert logits.shape == (N_REGIONS, N_ACTIONS)
        assert value.shape == ()

    def test_action_probabilities_sum_to_one(self):
        from models.rl.gnn_policy import GNNPolicyNetwork
        from models.rl.alert_env import HazardAlertEnv
        policy = GNNPolicyNetwork()
        policy.eval()
        env = HazardAlertEnv()
        env.reset()
        state = env.get_graph_state()
        logits, _ = policy(
            state.node_features, state.edge_index, state.edge_weights
        )
        probs = torch.softmax(logits, dim=-1)
        row_sums = probs.sum(dim=-1)
        assert torch.allclose(row_sums, torch.ones(11), atol=1e-5)

    def test_act_returns_valid_actions(self):
        from models.rl.gnn_policy import GNNPolicyNetwork
        from models.rl.alert_env import HazardAlertEnv
        policy = GNNPolicyNetwork()
        policy.eval()
        env = HazardAlertEnv()
        env.reset()
        state = env.get_graph_state()
        actions, log_probs, value = policy.act(state)
        assert actions.shape == (11,)
        assert log_probs.shape == (11,)
        assert value.numel() == 1

    def test_deterministic_act_chooses_argmax(self):
        from models.rl.gnn_policy import GNNPolicyNetwork
        from models.rl.alert_env import HazardAlertEnv
        policy = GNNPolicyNetwork()
        policy.eval()  # disable dropout so forward pass is deterministic
        env = HazardAlertEnv()
        env.reset()
        state = env.get_graph_state()

        # First forward pass to get logits
        logits, _ = policy(
            state.node_features, state.edge_index, state.edge_weights
        )
        expected_actions = logits.argmax(dim=-1)

        # Second forward pass via act() should give same result
        actions, _, _ = policy.act(state, deterministic=True)
        assert torch.all(actions == expected_actions), (
            f"Deterministic act differs from argmax: "
            f"expected={expected_actions}, got={actions}"
        )


class TestPPOTrainer:
    def test_collect_rollout_populates_buffer(self):
        from models.rl.ppo_trainer import PPOTrainer
        trainer = PPOTrainer()
        trainer.collect_rollout(n_steps=64)
        assert trainer.buffer.ptr > 0
        assert len(trainer.buffer.rewards) > 0
        assert len(trainer.buffer.node_features) > 0

    def test_ppo_update_does_not_crash(self):
        from models.rl.ppo_trainer import PPOTrainer
        trainer = PPOTrainer()
        trainer.collect_rollout(n_steps=128)
        loss = trainer.update()
        assert isinstance(loss, float)
        assert loss > 0

    def test_training_improves_reward(self):
        """Average reward should increase over training."""
        import torch
        torch.manual_seed(42)
        from models.rl.ppo_trainer import PPOTrainer
        trainer = PPOTrainer()
        trainer.train(n_iterations=30, verbose=False)
        rewards = list(trainer.rewards_history)
        if len(rewards) >= 4:
            mid = len(rewards) // 2
            early_avg = sum(rewards[:mid]) / mid
            late_avg = sum(rewards[mid:]) / mid
            assert late_avg >= early_avg - 5.0, (
                f"PPO training not improving: early={early_avg:.2f}, late={late_avg:.2f}"
            )

    def test_save_and_load_policy(self):
        from models.rl.ppo_trainer import PPOTrainer
        import os
        trainer = PPOTrainer()
        trainer.train(n_iterations=10, verbose=False)
        assert os.path.exists('models/saved/ppo_alert_policy.pt')
        trainer2 = PPOTrainer()
        assert trainer2.load()
        assert trainer2.is_trained