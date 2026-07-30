"""
Graph Attention Network (GAT) actor-critic for PPO.
Uses scatter-based attention aggregation for scalability.

Actor:  GATLayer(10→64) → GATLayer(64→64) → Linear(64→4 actions)
Critic: GATLayer(10→64) → GlobalMeanPool → Linear(64→1 value)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

N_FEATURES = 10
N_REGIONS = 11
N_ACTIONS = 4  # 0=none, 1=low, 2=med, 3=high alert
N_HEADS = 4  # Graph Attention heads
HIDDEN_DIM = 64


class GraphAttentionLayer(nn.Module):
    """
    Single Graph Attention Network (GAT) layer.
    Uses scatter-based aggregation — not dense N×N matrix.
    Attention score = LeakyReLU(a^T [Wh_i || Wh_j])
    """

    def __init__(self, in_features: int, out_features: int,
                 n_heads: int = 4, dropout: float = 0.2):
        super().__init__()
        self.out_features = out_features
        self.n_heads = n_heads
        self.head_dim = out_features // n_heads

        self.W = nn.Linear(in_features, out_features, bias=False)
        self.a = nn.Linear(2 * self.head_dim, 1, bias=False)
        self.dropout = nn.Dropout(dropout)
        self.leaky_relu = nn.LeakyReLU(0.2)

    def forward(
        self,
        x: torch.Tensor,  # (N, in_features)
        edge_index: torch.Tensor,  # (2, E)
        edge_weights: torch.Tensor  # (E,)
    ) -> torch.Tensor:  # (N, out_features)
        N = x.size(0)
        Wh = self.W(x)  # (N, out_features)
        Wh_heads = Wh.view(N, self.n_heads, self.head_dim)

        src, tgt = edge_index  # (E,), (E,)
        Wh_src = Wh_heads[src]  # (E, heads, head_dim)
        Wh_tgt = Wh_heads[tgt]  # (E, heads, head_dim)

        concat = torch.cat([Wh_src, Wh_tgt], dim=-1)  # (E, heads, 2*head_dim)
        # Attention scores
        e = self.leaky_relu(self.a(concat)).squeeze(-1)  # (E, heads)
        # Weight by causal edge strength
        e = e * edge_weights.unsqueeze(-1)

        # Scatter-based softmax over incoming edges per node
        alpha = torch.zeros(N, N, self.n_heads, device=x.device)
        alpha[tgt, src] = e
        alpha = F.softmax(alpha + (alpha == 0).float() * -1e9, dim=1)
        alpha = self.dropout(alpha)

        # Aggregate
        out = torch.zeros(N, self.n_heads, self.head_dim, device=x.device)
        for h in range(self.n_heads):
            out[:, h] = alpha[:, :, h] @ Wh_heads[:, h]
        return F.elu(out.reshape(N, -1))


class GNNPolicyNetwork(nn.Module):
    """
    Graph Attention Network actor-critic for alert policy.

    Actor:  GATLayer(10→64) → GATLayer(64→64) → Linear(64→4 actions)
    Critic: GATLayer(10→64) → GlobalMeanPool → Linear(64→1 value)

    Outputs action logits per region (actor) and state value (critic).
    PPO uses both for policy update + value function baseline.
    """

    def __init__(self):
        super().__init__()
        # Shared GNN backbone
        self.gat1 = GraphAttentionLayer(N_FEATURES, HIDDEN_DIM, N_HEADS)
        self.gat2 = GraphAttentionLayer(HIDDEN_DIM, HIDDEN_DIM, N_HEADS)
        self.norm1 = nn.LayerNorm(HIDDEN_DIM)
        self.norm2 = nn.LayerNorm(HIDDEN_DIM)

        # Actor head: action logits per region
        self.actor_head = nn.Sequential(
            nn.Linear(HIDDEN_DIM, 32),
            nn.ReLU(),
            nn.Linear(32, N_ACTIONS)
        )

        # Critic head: single scalar value
        self.critic_head = nn.Sequential(
            nn.Linear(HIDDEN_DIM, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )

    def forward(
        self,
        node_features: torch.Tensor,  # (N, 10)
        edge_index: torch.Tensor,  # (2, E)
        edge_weights: torch.Tensor  # (E,)
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Returns:
          action_logits: (N, N_ACTIONS) — per region action distribution
          state_value:   (1,)           — baseline value estimate
        """
        x = self.gat1(node_features, edge_index, edge_weights)
        x = self.norm1(x)
        x = F.dropout(x, p=0.1, training=self.training)
        x = self.gat2(x, edge_index, edge_weights)
        x = self.norm2(x)

        action_logits = self.actor_head(x)  # (N, 4)
        state_value = self.critic_head(x.mean(0)).squeeze(-1)  # global mean pool → scalar
        return action_logits, state_value

    def act(
        self, state: 'GraphState', deterministic: bool = False
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Sample action from policy.
        Returns: (actions, log_probs, value)
        actions:   (N,) int — alert level per region
        log_probs: (N,) float — log probability of chosen action
        value:     scalar
        """
        logits, value = self.forward(
            state.node_features,
            state.edge_index,
            state.edge_weights
        )
        dist = torch.distributions.Categorical(logits=logits)
        if deterministic:
            actions = logits.argmax(dim=-1)
        else:
            actions = dist.sample()
        log_probs = dist.log_prob(actions)
        return actions, log_probs, value.squeeze()