"""
Saves weekly Neo4j graph state as a snapshot node.
This creates a temporal graph — the graph evolves over time.
DRL training uses historical snapshots as experience replay.
Each snapshot captures: node features + edge weights + risk scores.
"""

import json
from datetime import datetime


async def save_weekly_snapshot(neo4j_session) -> str:
    """
    Creates GraphSnapshot node with serialised state.
    Returns snapshot_id.
    """
    snapshot_id = f'snap_{datetime.utcnow().strftime("%Y%m%dT%H%M")}'

    # Fetch current state
    result = await neo4j_session.run(
        'MATCH (r:Region) '
        'OPTIONAL MATCH (r)-[:IN_REGIME]->(h:HazardRegime) '
        'RETURN r.id as id, r.name as name, '
        '       r.current_risk_score as risk, '
        '       r.pagerank_score as pr, '
        '       h.name as regime'
    )
    nodes = [dict(record) async for record in result]

    result2 = await neo4j_session.run(
        'MATCH (e:CausalEdge {active: true}) '
        'RETURN e.region_id as region, '
        '       e.source_variable as src, '
        '       e.target_variable as tgt, '
        '       e.weight as w, e.lag_days as lag'
    )
    edges = [dict(record) async for record in result2]

    snapshot_data = json.dumps({
        'nodes': nodes, 'edges': edges,
        'timestamp': datetime.utcnow().isoformat()
    })

    await neo4j_session.run(
        'MERGE (s:GraphSnapshot {id: $sid}) '
        'SET s.data_json = $data, '
        '    s.created_at = $now, '
        '    s.node_count = $nc, '
        '    s.edge_count = $ec',
        sid=snapshot_id,
        data=snapshot_data,
        now=datetime.utcnow().isoformat(),
        nc=len(nodes),
        ec=len(edges)
    )
    # Link to previous snapshot for temporal chain
    await neo4j_session.run(
        'MATCH (s:GraphSnapshot {id: $sid}) '
        'MATCH (prev:GraphSnapshot) '
        'WHERE prev.id <> $sid '
        'WITH s, prev ORDER BY prev.created_at DESC LIMIT 1 '
        'MERGE (prev)-[:NEXT_SNAPSHOT]->(s)',
        sid=snapshot_id
    )
    return snapshot_id


async def load_snapshots_for_training(
    neo4j_session, n_weeks: int = 52
) -> list[dict]:
    """
    Load last n_weeks snapshots for DRL experience replay.
    Returns list of snapshot dicts ordered oldest first.
    """
    result = await neo4j_session.run(
        'MATCH (s:GraphSnapshot) '
        'RETURN s.data_json as data, s.created_at as ts '
        'ORDER BY s.created_at DESC LIMIT $n',
        n=n_weeks
    )
    snapshots = []
    async for record in result:
        snapshots.append({
            'data': json.loads(record['data']),
            'timestamp': record['ts']
        })
    return list(reversed(snapshots))  # oldest first