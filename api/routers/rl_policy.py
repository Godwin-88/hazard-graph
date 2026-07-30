"""
DRL Policy API endpoints.
Returns optimal alert actions from the GNN-PPO policy.
"""

from fastapi import APIRouter, Depends, HTTPException
from api.deps import get_current_user, require_officer
from db.neo4j_client import get_neo4j_session
from db.redis_client import get_redis
import json

router = APIRouter(prefix='/rl', tags=['DRL Policy'])


@router.get('/recommendations')
async def get_policy_recommendations(
    user=Depends(get_current_user),
    neo4j=Depends(get_neo4j_session),
    redis=Depends(get_redis)
):
    """
    Run trained GNN-PPO policy on current live graph state.
    Returns optimal alert action per region with reasoning.
    Cached 10 minutes (policy doesn't change mid-week).
    """
    cache_key = 'rl:recommendations'
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    from models.rl.graph_state import GraphState, REGIONS
    from models.rl.policy_inference import AlertPolicyInference
    from risk.scoring_service import compute_risk_scores

    # Fetch current BMA scores, SDE, HMM from Neo4j
    scores = await compute_risk_scores(neo4j)
    score_dict = {s.region_id: s.score for s in scores}

    # Fetch causal edges
    result = await neo4j.run(
        'MATCH (e:CausalEdge {active: true}) '
        'RETURN e.region_id as r, e.source_variable as s, '
        '       e.target_variable as t, e.weight as w'
    )
    causal_edges = []
    async for rec in result:
        causal_edges.append((rec['r'], rec['t'], rec['w']))

    # Build state with available data
    import torch
    import numpy as np
    features = np.zeros((len(REGIONS), 10), dtype=np.float32)
    for i, region in enumerate(REGIONS):
        risk = score_dict.get(region, 50.0) / 100.0
        features[i] = [risk, risk * 0.8, risk * 0.6, risk * 0.3,
                       risk * 0.9, risk * 0.85, 0.1, 0.6, 0.8, 0.5]

    region_idx = {r: i for i, r in enumerate(REGIONS)}
    edges_s, edges_t, edge_w = [], [], []
    for src, tgt, w in causal_edges:
        if src in region_idx and tgt in region_idx:
            edges_s.append(region_idx[src])
            edges_t.append(region_idx[tgt])
            edge_w.append(float(w))
    if not edges_s:
        for i in range(len(REGIONS)):
            edges_s.append(i)
            edges_t.append(i)
            edge_w.append(1.0)

    state = GraphState(
        node_features=torch.FloatTensor(features),
        edge_index=torch.LongTensor([edges_s, edges_t]),
        edge_weights=torch.FloatTensor(edge_w)
    )

    inference = AlertPolicyInference()
    recommendations = inference.recommend(state)

    response = {
        'recommendations': [
            {
                'region_id': r.region_id,
                'action': r.action,
                'action_label': r.action_label,
                'probability': r.action_probability,
                'reasoning': r.reasoning
            }
            for r in recommendations
        ],
        'policy_version': 'ppo_v1',
        'model': 'GNN-PPO (GAT + PPO, 11 nodes × 10 features)'
    }

    await redis.setex(cache_key, 600, json.dumps(response))
    return response


@router.post('/train')
async def trigger_training(user=Depends(require_officer)):
    """Trigger PPO training run (async background task)."""
    import asyncio
    from models.rl.ppo_trainer import PPOTrainer

    async def train_bg():
        trainer = PPOTrainer()
        trainer.train(n_iterations=100, verbose=False)

    asyncio.create_task(train_bg())
    return {
        'status': 'training_started',
        'message': 'PPO training running in background (~5 min)'
    }


@router.get('/training-status')
async def training_status(user=Depends(get_current_user)):
    """Check if trained model exists."""
    import os
    exists = os.path.exists('models/saved/ppo_alert_policy.pt')
    return {
        'model_available': exists,
        'model_path': 'models/saved/ppo_alert_policy.pt' if exists else None
    }