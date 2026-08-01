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


def _infer_node_type(props: dict) -> str:
    """Infer a node type from its properties when labels are missing.

    Safety net so nodes are never reported as "Unknown" even if the
    driver returns plain dicts without label metadata. Covers every
    node label defined in migrations/001_schema.cypher and node_writers.
    """
    if "severity_level" in props:
        return "HazardRegime"
    if "spi_30d" in props or "anomaly_pct" in props or "dekad" in props:
        return "RainfallSignal"
    if "price_usd" in props or "pct_change_30d" in props or "commodity" in props:
        return "FoodPriceSignal"
    if "phase" in props and "population_affected" in props:
        return "IPCPhaseSignal"
    if "country" in props or "admin_level" in props or "current_risk_score" in props:
        return "Region"
    if "source_variable" in props and "target_variable" in props:
        return "CausalEdge"
    if "hazard_type" in props and "severity" in props:
        return "ForecastSignal"
    if "p_crisis" in props or "shap" in props:
        return "MLForecast"
    if "category" in props or "name" in props and "hazard" in str(props.get("id", "")).lower():
        return "HazardType"
    if "lead_time_days" in props or "description" in props and "strategy" in str(props.get("id", "")).lower():
        return "InterventionStrategy"
    if "url" in props or "ingested_at" in props or "record_count" in props:
        return "DataSource"
    if "message_text" in props or "risk_score_at_trigger" in props:
        return "Alert"
    if "member_count" in props or "label" in props and "cluster" in str(props.get("id", "")).lower():
        return "HazardCluster"
    if "score" in props and "model" in str(props.get("id", "")).lower():
        return "BMAScore"
    return "Unknown"


def _transform_node(record: dict) -> dict:
    """Transform a Neo4j node record to frontend-friendly format.

    Handles both real driver Node objects (returned by record.data())
    and plain dict fallbacks. The Neo4j async driver exposes labels and
    element_id as attributes, not dict keys. A property-based type
    inference fallback guarantees nodes are never "Unknown".
    """
    n = record.get("n", record)
    if not n:
        return None

    # Case 1: real driver Node object — labels/element_id are attributes.
    # Guard against a "Unknown" sentinel label so the property-based
    # inference still runs when the node has no real labels.
    if hasattr(n, "labels") and hasattr(n, "element_id"):
        labels = [lb for lb in n.labels if lb and lb != "Unknown"]
        props = dict(getattr(n, "_properties", {}) or {})
        node_type = labels[0] if labels else _infer_node_type(props)
        node_id = props.get("id") or n.element_id
        label = props.get("name") or props.get("title") or node_type
        return {
            "id": str(node_id),
            "label": str(label),
            "type": node_type,
            "properties": props,
        }

    # Case 2: plain dict — labels/elementId may be keys or absent.
    # If labels resolve to ["Unknown"], fall through to property-based
    # inference instead of reporting the sentinel unchanged.
    props = {k: v for k, v in n.items() if k not in ("labels", "_labels", "_id", "elementId")}
    raw_labels = n.get("labels", n.get("_labels", ["Unknown"]))
    labels = [lb for lb in raw_labels if lb and lb != "Unknown"]
    node_type = labels[0] if labels else _infer_node_type(props)
    node_id = props.get("id") or n.get("elementId") or n.get("_id") or str(id(n))
    label = props.get("name") or props.get("title") or node_type
    return {
        "id": str(node_id),
        "label": str(label),
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

    Cached in Redis for 5 minutes. Cache key is versioned (v2) so any
    stale pre-fix "Unknown" data cached under the old key is ignored.
    """
    cached = await redis_client.get("graph:nodes:v2")
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    # Fresh data computed below; drop stale cached copy that may contain
    # pre-fix "Unknown" node types / mismatched ids.
    try:
        await redis_client.delete("graph:nodes:v2")
        await redis_client.delete("graph:edges:v2")
    except Exception as exc:
        logger.warning("Failed to clear stale graph cache: %s", exc)

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
            if node:
                nodes_map[node["id"]] = node

        # Add target node
        if "m" in record and record["m"]:
            node = _transform_node({"n": record["m"]})
            if node:
                nodes_map[node["id"]] = node

        # Add edge
        if "r" in record and record["r"]:
            edge = _transform_edge({"r": record["r"]})
            if edge:
                edges.append(edge)

    response = {"nodes": list(nodes_map.values()), "edges": edges}

    try:
        await redis_client.set("graph:nodes:v2", json.dumps(response, default=str), ttl=300)
    except Exception as exc:
        logger.warning("Failed to cache graph nodes: %s", exc)

    return response


@router.get("/graph/edges")
async def get_all_edges():
    """Return all active edges for graph visualisation.

    Cached in Redis for 5 minutes. Cache key is versioned (v2) so any
    stale pre-fix data cached under the old key is ignored.
    """
    cached = await redis_client.get("graph:edges:v2")
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
        await redis_client.set("graph:edges:v2", json.dumps(edges, default=str), ttl=300)
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
            if node_data:
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
            if node_data:
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