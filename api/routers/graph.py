"""HazardGraph — Graph query API endpoints.

All endpoints use Redis caching (5-min TTL unless noted).
Returns Neo4j graph data formatted for React frontend visualisation.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from db.neo4j_client import neo4j_client
from db.redis_client import redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["graph"])


def _transform_node(record: dict) -> dict:
    """Transform a Neo4j node record to frontend-friendly format."""
    n = record.get("n", record)
    labels = list(n.get("labels", n.get("_labels", ["Unknown"])))
    props = {k: v for k, v in n.items() if k not in ("labels", "_labels", "_id")}
    node_type = labels[0] if labels else "Unknown"
    return {
        "id": props.get("id", n.get("elementId", str(id(n)))),
        "label": props.get("name", props.get("title", labels[0] if labels else "Node")),
        "type": node_type,
        "properties": props,
    }


def _transform_edge(record: dict) -> Optional[dict]:
    """Transform a Neo4j relationship record to frontend-friendly format."""
    r = record.get("r", record)
    if not r:
        return None
    # Neo4j async driver may return a tuple (start, rel, end) instead of a bare
    # Relationship object when the Cypher query returns path-like patterns.
    if isinstance(r, tuple):
        r = r[1]  # index 1 is always the relationship in a 3-tuple
    # Handle Neo4j Relationship object by converting to a plain dict
    if hasattr(r, "_properties"):
        return {
            "source": r.start_node.element_id if hasattr(r, "start_node") else "",
            "target": r.end_node.element_id if hasattr(r, "end_node") else "",
            "type": r.type,
            "weight": r._properties.get("weight", 1.0),
            "lag_days": r._properties.get("lag_days", 0),
        }
    # Handle case where r is a plain string (relationship type)
    if isinstance(r, str):
        return {
            "source": record.get("source", ""),
            "target": record.get("target", ""),
            "type": r,
            "weight": 1.0,
            "lag_days": 0,
        }
    # Fallback: treat as plain dict
    rel_type = r.get("type", r.get("_type", "RELATED_TO"))
    props = {k: v for k, v in r.items() if k not in ("type", "_type", "_id")}
    return {
        "source": r.get("startNodeElementId", r.get("_start", "")),
        "target": r.get("endNodeElementId", r.get("_end", "")),
        "type": rel_type,
        "weight": props.get("weight", 1.0),
        "lag_days": props.get("lag_days", 0),
    }


@router.get("/graph/nodes")
async def get_all_nodes():
    """Return all active nodes + edges for graph visualisation.

    Cached in Redis for 5 minutes.
    """
    cached = await redis_client.get("graph:nodes")
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    query = """
    MATCH (n) WHERE n.active IS NULL OR n.active <> false
    OPTIONAL MATCH (n)-[r]->(m)
    RETURN n, r, m LIMIT 500
    """
    try:
        results = await neo4j_client.execute_read(query)
    except Exception as exc:
        logger.error("Graph nodes query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Neo4j query failed")

    nodes_map = {}
    edges = []

    for record in results:
        # Add source node
        if "n" in record and record["n"]:
            node = _transform_node({"n": record["n"]})
            nodes_map[node["id"]] = node

        # Add target node
        if "m" in record and record["m"]:
            node = _transform_node({"n": record["m"]})
            nodes_map[node["id"]] = node

        # Add edge
        if "r" in record and record["r"]:
            edge = _transform_edge({"r": record["r"]})
            if edge:
                edges.append(edge)

    response = {"nodes": list(nodes_map.values()), "edges": edges}

    try:
        await redis_client.set("graph:nodes", json.dumps(response, default=str), ttl=300)
    except Exception as exc:
        logger.warning("Failed to cache graph nodes: %s", exc)

    return response


@router.get("/graph/edges")
async def get_all_edges():
    """Return all active edges for graph visualisation.

    Cached in Redis for 5 minutes.
    """
    cached = await redis_client.get("graph:edges")
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    query = """
    MATCH (n) WHERE n.active IS NULL OR n.active <> false
    OPTIONAL MATCH (n)-[r]->(m)
    RETURN n, r, m LIMIT 500
    """
    try:
        results = await neo4j_client.execute_read(query)
    except Exception as exc:
        logger.error("Graph edges query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Neo4j query failed")

    edges = []
    for record in results:
        if "r" in record and record["r"]:
            edge = _transform_edge({"r": record["r"]})
            if edge:
                edges.append(edge)

    try:
        await redis_client.set("graph:edges", json.dumps(edges, default=str), ttl=300)
    except Exception as exc:
        logger.warning("Failed to cache graph edges: %s", exc)

    return edges


@router.get("/graph/region/{region_id}")
async def get_region_subgraph(region_id: str):
    """Return subgraph centred on one region (depth 2).

    Cached in Redis for 2 minutes.
    """
    cache_key = f"graph:region:{region_id}"
    cached = await redis_client.get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    query = """
    MATCH path = (r:Region {id: $region_id})-[*1..2]-(n)
    RETURN path
    """
    try:
        results = await neo4j_client.execute_read(query, {"region_id": region_id})
    except Exception as exc:
        logger.error("Region subgraph query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Neo4j query failed")

    nodes_map = {}
    edges = []

    for record in results:
        path = record.get("path")
        if not path:
            continue

        # Process nodes in path
        for node in path.get("nodes", []):
            node_data = _transform_node({"n": node})
            nodes_map[node_data["id"]] = node_data

        # Process relationships in path
        for rel in path.get("relationships", []):
            edge = _transform_edge({"r": rel})
            if edge:
                edges.append(edge)

    response = {"nodes": list(nodes_map.values()), "edges": edges}

    try:
        await redis_client.set(cache_key, json.dumps(response, default=str), ttl=120)
    except Exception as exc:
        logger.warning("Failed to cache region subgraph: %s", exc)

    return response


@router.get("/graph/causal-edges")
async def get_causal_edges():
    """Return all active CausalEdge nodes.

    Cached in Redis for 10 minutes.
    """
    cached = await redis_client.get("graph:causal-edges")
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    query = """
    MATCH (e:CausalEdge) WHERE e.active IS NULL OR e.active = true
    RETURN e ORDER BY e.weight DESC
    """
    try:
        results = await neo4j_client.execute_read(query)
    except Exception as exc:
        logger.error("Causal edges query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Neo4j query failed")

    edges = []
    for record in results:
        e = record.get("e", {})
        edges.append({
            "id": e.get("id", ""),
            "source_variable": e.get("source_variable", ""),
            "target_variable": e.get("target_variable", ""),
            "weight": e.get("weight", 0.0),
            "lag_weeks": e.get("lag_weeks", 0),
            "p_value": e.get("p_value", 1.0),
            "region_id": e.get("region_id", ""),
            "method": e.get("method", "VARLiNGAM"),
            "discovered_at": e.get("discovered_at", ""),
        })

    try:
        await redis_client.set("graph:causal-edges", json.dumps(edges, default=str), ttl=600)
    except Exception as exc:
        logger.warning("Failed to cache causal edges: %s", exc)

    return edges


@router.get("/graph/regimes")
async def get_regimes():
    """Return all regions with their current regime and posterior probs.

    Pulls Region.current_regime from Neo4j + posteriors from Redis.
    Falls back to Neo4j if Redis miss.
    """
    query = """
    MATCH (r:Region)
    RETURN r.id AS id, r.name AS name, r.country AS country,
           r.current_regime AS current_regime
    ORDER BY r.name
    """
    try:
        regions = await neo4j_client.execute_read(query)
    except Exception as exc:
        logger.error("Regimes query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Neo4j query failed")

    result = []
    for region in regions:
        region_id = region.get("id", "")
        regime = region.get("current_regime", "Baseline")

        # Try Redis for posteriors
        posteriors = None
        cache_key = f"regime_posteriors:{region_id}"
        cached = await redis_client.get(cache_key)
        if cached:
            try:
                cached_data = json.loads(cached)
                posteriors = cached_data.get("posteriors")
                regime = cached_data.get("regime", regime)
            except Exception:
                pass

        result.append({
            "id": region_id,
            "name": region.get("name", ""),
            "country": region.get("country", ""),
            "current_regime": regime,
            "posteriors": posteriors or {
                "Baseline": 0.5,
                "DroughtOnset": 0.2,
                "SevereDrought": 0.1,
                "FloodWatch": 0.1,
                "FloodEmergency": 0.1,
            },
        })

    return {"regions": result}


@router.get("/graph/causal-chain/{region_id}/{hazard_type}")
async def get_causal_chain(region_id: str, hazard_type: str):
    """Trace the full causal chain leading to a hazard type in a region.

    Cached in Redis for 5 minutes.
    """
    cache_key = f"graph:causal-chain:{region_id}:{hazard_type}"
    cached = await redis_client.get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    # Map hazard type to target signal type
    hazard_to_signal = {
        "drought": "RainfallSignal",
        "flood": "RainfallSignal",
        "locust": "RainfallSignal",
        "conflict": "FoodPriceSignal",
        "heatwave": "RainfallSignal",
        "disease_outbreak": "IPCPhaseSignal",
        "storm": "RainfallSignal",
        "landslide": "RainfallSignal",
        "frost": "RainfallSignal",
        "wildfire": "RainfallSignal",
        "market_shock": "FoodPriceSignal",
    }
    target_label = hazard_to_signal.get(hazard_type, "IPCPhaseSignal")

    query = f"""
    MATCH path = (s)-[:CAUSES*1..4]->(h:{target_label})
    WHERE s.region_id = $region_id
    RETURN path, [r in relationships(path) | r.weight] as weights
    LIMIT 10
    """
    try:
        results = await neo4j_client.execute_read(query, {"region_id": region_id})
    except Exception as exc:
        logger.error("Causal chain query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Neo4j query failed")

    chains = []
    for record in results:
        path = record.get("path")
        weights = record.get("weights", [])
        if not path:
            continue

        chain_nodes = []
        for node in path.get("nodes", []):
            node_data = _transform_node({"n": node})
            chain_nodes.append(node_data)

        cumulative_weight = sum(abs(w) for w in weights) if weights else 0.0

        chains.append({
            "nodes": chain_nodes,
            "weights": [float(w) for w in weights],
            "cumulative_weight": round(cumulative_weight, 4),
        })

    response = {"region_id": region_id, "hazard_type": hazard_type, "chains": chains}

    try:
        await redis_client.set(cache_key, json.dumps(response, default=str), ttl=300)
    except Exception as exc:
        logger.warning("Failed to cache causal chain: %s", exc)

    return response