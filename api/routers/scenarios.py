"""
Scenarios API — cascade simulation, cluster detection, temporal graph.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth.jwt_service import get_current_user, require_officer
from db.neo4j_client import get_neo4j_session
from api.deps import get_redis
import json

router = APIRouter(prefix='/api/v1/scenarios', tags=['Scenarios'])


class CascadeRequest(BaseModel):
    source_region: str
    horizon_weeks: int = 8
    n_paths: int = 500


@router.post('/cascade')
async def run_cascade(
    req: CascadeRequest,
    user=Depends(get_current_user),
    neo4j=Depends(get_neo4j_session)
):
    """Run SIR cascade simulation from a source region."""
    from models.network.contagion_cascade import SIRCascadeSimulator
    from risk.scoring_service import compute_risk_scores

    scores = await compute_risk_scores(neo4j)
    risk_scores = {s.region_id: s.score for s in scores}
    vulnerability_multipliers = {s.region_id: 1.5 for s in scores}

    sim = SIRCascadeSimulator()
    result = sim.compute_cascade_result(
        source_region=req.source_region,
        risk_scores=risk_scores,
        vulnerability_multipliers=vulnerability_multipliers,
        n_paths=req.n_paths,
        horizon_weeks=req.horizon_weeks
    )

    await sim.write_to_neo4j(result, neo4j)

    return {
        'source_region': result.source_region,
        'horizon_weeks': result.horizon_weeks,
        'cascade_probabilities': result.cascade_probabilities,
        'critical_intervention_node': result.critical_intervention_node,
        'expected_affected_population_millions': result.expected_affected_population,
        'simulation_paths': result.simulation_paths,
        'simulated_at': result.simulated_at
    }


@router.get('/clusters')
async def get_clusters(
    user=Depends(get_current_user),
    neo4j=Depends(get_neo4j_session),
    redis=Depends(get_redis)
):
    """Return current HazardCluster nodes from Neo4j."""
    cache_key = 'scenarios:clusters'
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    result = await neo4j.run(
        'MATCH (c:HazardCluster) '
        'OPTIONAL MATCH (r:Region)-[:BELONGS_TO_CLUSTER]->(c) '
        'RETURN c.id as id, c.label as label, '
        '       c.dominant_hazard as dominant_hazard, '
        '       c.cluster_risk_score as risk_score, '
        '       c.centroid_lat as lat, c.centroid_lon as lon, '
        '       c.member_count as member_count, '
        '       COLLECT(DISTINCT r.id) as member_regions'
    )
    clusters = [dict(record) async for record in result]

    response = {'clusters': clusters}
    await redis.set(cache_key, json.dumps(response), ttl=1800)
    return response


@router.post('/clusters/refresh')
async def refresh_clusters(
    user=Depends(require_officer),
    neo4j=Depends(get_neo4j_session)
):
    """Re-run Louvain detection and write clusters to Neo4j."""
    from models.network.community_detection import LouvainHazardClustering
    from risk.scoring_service import compute_risk_scores
    from config.settings import settings
    from groq import AsyncGroq

    scores = await compute_risk_scores(neo4j)
    risk_scores = {s.region_id: s.score for s in scores}
    regimes = {s.region_id: s.current_regime for s in scores}
    spi_values = {s.region_id: 0.0 for s in scores}

    # Fetch causal edge density
    result = await neo4j.run(
        'MATCH (e:CausalEdge {active: true}) '
        'RETURN e.region_id as r, e.source_variable as s, '
        '       e.target_variable as t, e.weight as w'
    )
    causal_density = {}
    async for rec in result:
        causal_density[(rec['r'], rec['t'])] = float(rec['w'])

    groq_client = AsyncGroq(api_key=settings.groq_api_key)
    clustering = LouvainHazardClustering()
    clusters = await clustering.run(
        risk_scores, regimes, spi_values,
        causal_density, neo4j, groq_client
    )

    return {
        'status': 'clusters_refreshed',
        'cluster_count': len(clusters),
        'clusters': [
            {
                'cluster_id': c.cluster_id,
                'label': c.label,
                'member_regions': c.member_regions,
                'dominant_hazard': c.dominant_hazard,
                'cluster_risk_score': c.cluster_risk_score
            }
            for c in clusters
        ]
    }


@router.get('/temporal-graph')
async def get_temporal_graph(
    user=Depends(get_current_user),
    neo4j=Depends(get_neo4j_session)
):
    """Return last 12 GraphSnapshot nodes for timeline animation."""
    from graph.temporal_snapshots import load_snapshots_for_training

    snapshots = await load_snapshots_for_training(neo4j, n_weeks=12)
    timeline = []
    for snap in snapshots:
        data = snap['data']
        nodes = data.get('nodes', [])
        risks = [n.get('risk', 0) for n in nodes if n.get('risk') is not None]
        timeline.append({
            'timestamp': snap['timestamp'],
            'node_count': len(nodes),
            'edge_count': len(data.get('edges', [])),
            'avg_risk': float(sum(risks) / len(risks)) if risks else 0,
            'high_risk_regions': sum(1 for r in risks if r > 65)
        })

    return {'snapshots': timeline}