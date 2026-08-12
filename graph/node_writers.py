"""HazardGraph — All Neo4j MERGE upsert functions.

All queries use parameterised Cypher — no f-string injection.
"""

import logging
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from db.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


async def upsert_forecast_signal(
    signal_id: str,
    hazard_type: str,
    severity: float,
    horizon_days: int,
    confidence_pct: float,
    region_id: Optional[str] = None,
) -> dict:
    """Upsert a ForecastSignal node and link to Region if provided."""
    query = """
    MERGE (fs:ForecastSignal {id: $id})
    SET fs.hazard_type = $hazard_type,
        fs.severity = $severity,
        fs.horizon_days = $horizon_days,
        fs.confidence_pct = $confidence_pct,
        fs.created_at = $created_at
    RETURN fs.id AS id, fs.hazard_type AS hazard_type
    """
    params = {
        "id": signal_id,
        "hazard_type": hazard_type,
        "severity": severity,
        "horizon_days": horizon_days,
        "confidence_pct": confidence_pct,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await neo4j_client.execute_write(query, params)
    logger.info("Upserted ForecastSignal %s (hazard=%s)", signal_id, hazard_type)
    return result[0] if result else {"id": signal_id}


async def link_signal_to_region(signal_id: str, region_id: str) -> None:
    """Create MEASURED_IN relationship between a signal and a Region."""
    query = """
    MATCH (s:ForecastSignal {id: $signal_id})
    MATCH (r:Region {id: $region_id})
    MERGE (s)-[:MEASURED_IN]->(r)
    """
    await neo4j_client.execute_write(query, {"signal_id": signal_id, "region_id": region_id})
    logger.debug("Linked %s -> MEASURED_IN -> %s", signal_id, region_id)


async def upsert_data_source(
    source_id: str,
    name: str,
    url: str,
    record_count: int = 0,
    hash_value: str = "",
) -> dict:
    """Upsert a DataSource node."""
    query = """
    MERGE (ds:DataSource {id: $id})
    SET ds.name = $name,
        ds.url = $url,
        ds.ingested_at = $ingested_at,
        ds.record_count = $record_count,
        ds.hash = $hash_value
    RETURN ds.id AS id, ds.name AS name
    """
    params = {
        "id": source_id,
        "name": name,
        "url": url,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "record_count": record_count,
        "hash_value": hash_value,
    }
    result = await neo4j_client.execute_write(query, params)
    return result[0] if result else {"id": source_id}


async def link_sourced_from(node_id: str, source_id: str) -> None:
    """Create SOURCED_FROM relationship from any node to a DataSource."""
    query = """
    MATCH (n {id: $node_id})
    MATCH (ds:DataSource {id: $source_id})
    MERGE (n)-[:SOURCED_FROM]->(ds)
    """
    await neo4j_client.execute_write(query, {"node_id": node_id, "source_id": source_id})
    logger.debug("Linked %s -> SOURCED_FROM -> %s", node_id, source_id)


async def upsert_rainfall_signal(
    signal_id: str,
    spi_30d: float,
    spi_30d_smoothed: float,
    anomaly_pct: float,
    dekad: str,
    date: str,
    region_id: str,
) -> dict:
    """Upsert a RainfallSignal node and link to Region."""
    query = """
    MERGE (rs:RainfallSignal {id: $id})
    SET rs.spi_30d = $spi_30d,
        rs.spi_30d_smoothed = $spi_30d_smoothed,
        rs.anomaly_pct = $anomaly_pct,
        rs.dekad = $dekad,
        rs.date = $date,
        rs.region_id = $region_id
    RETURN rs.id AS id
    """
    params = {
        "id": signal_id,
        "spi_30d": spi_30d,
        "spi_30d_smoothed": spi_30d_smoothed,
        "anomaly_pct": anomaly_pct,
        "dekad": dekad,
        "date": date,
        "region_id": region_id,
    }
    result = await neo4j_client.execute_write(query, params)
    return result[0] if result else {"id": signal_id}


async def upsert_food_price_signal(
    signal_id: str,
    commodity: str,
    market: str,
    price_usd: float,
    pct_change_30d: float,
    date: str,
    region_id: str,
) -> dict:
    """Upsert a FoodPriceSignal node and link to Region."""
    query = """
    MERGE (fps:FoodPriceSignal {id: $id})
    SET fps.commodity = $commodity,
        fps.market = $market,
        fps.price_usd = $price_usd,
        fps.pct_change_30d = $pct_change_30d,
        fps.date = $date,
        fps.region_id = $region_id
    RETURN fps.id AS id
    """
    params = {
        "id": signal_id,
        "commodity": commodity,
        "market": market,
        "price_usd": price_usd,
        "pct_change_30d": pct_change_30d,
        "date": date,
        "region_id": region_id,
    }
    result = await neo4j_client.execute_write(query, params)
    return result[0] if result else {"id": signal_id}


async def upsert_ipc_phase_signal(
    signal_id: str,
    phase: int,
    population_affected: int,
    reference_date: str,
    region_id: str,
) -> dict:
    """Upsert an IPCPhaseSignal node."""
    query = """
    MERGE (ipc:IPCPhaseSignal {id: $id})
    SET ipc.phase = $phase,
        ipc.population_affected = $population_affected,
        ipc.reference_date = $reference_date,
        ipc.region_id = $region_id
    RETURN ipc.id AS id
    """
    params = {
        "id": signal_id,
        "phase": phase,
        "population_affected": population_affected,
        "reference_date": reference_date,
        "region_id": region_id,
    }
    result = await neo4j_client.execute_write(query, params)
    return result[0] if result else {"id": signal_id}


async def upsert_alert(
    alert_id: str,
    region_id: str,
    language: str,
    message_text: str,
    risk_score_at_trigger: float,
    kelly_priority: float,
    status: str = "pending",
) -> dict:
    """Upsert an Alert node."""
    query = """
    MERGE (a:Alert {id: $id})
    SET a.region_id = $region_id,
        a.language = $language,
        a.message_text = $message_text,
        a.risk_score_at_trigger = $risk_score_at_trigger,
        a.kelly_priority = $kelly_priority,
        a.generated_at = $generated_at,
        a.status = $status,
        a.sent_count = 0,
        a.delivered_count = 0
    RETURN a.id AS id, a.status AS status
    """
    params = {
        "id": alert_id,
        "region_id": region_id,
        "language": language,
        "message_text": message_text,
        "risk_score_at_trigger": risk_score_at_trigger,
        "kelly_priority": kelly_priority,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
    }
    result = await neo4j_client.execute_write(query, params)
    logger.info("Upserted Alert %s for region %s", alert_id, region_id)
    return result[0] if result else {"id": alert_id}


def make_signal_id(source: str, hazard_type: str, date_str: str) -> str:
    """Generate a deterministic signal ID from source, hazard, and date."""
    raw = f"{source}:{hazard_type}:{date_str}"
    return f"signal_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


async def upsert_conflict_signal(
    signal_id: str,
    events_count: int,
    fatalities: int,
    event_type: str,
    location: str,
    event_date: str,
    region_id: str,
) -> dict:
    """Upsert a ConflictSignal node and link to Region.

    ACLED-derived conflict events aggregated per week/admin-area, the
    missing causal driver for Somalia/South Sudan/Sudan food insecurity.
    """
    query = """
    MERGE (cs:ConflictSignal {id: $id})
    SET cs.events_count = $events_count,
        cs.fatalities = $fatalities,
        cs.event_type = $event_type,
        cs.location = $location,
        cs.event_date = $event_date,
        cs.region_id = $region_id
    RETURN cs.id AS id
    """
    params = {
        "id": signal_id,
        "events_count": events_count,
        "fatalities": fatalities,
        "event_type": event_type,
        "location": location,
        "event_date": event_date,
        "region_id": region_id,
    }
    result = await neo4j_client.execute_write(query, params)
    return result[0] if result else {"id": signal_id}


async def upsert_ndvi_signal(
    signal_id: str,
    ndvi_value: float,
    anomaly: float,
    date: str,
    region_id: str,
) -> dict:
    """Upsert an NDVISignal node and link to Region.

    NDVI greenness from WFP/HDX datasets (or MODIS when available).
    """
    query = """
    MERGE (ns:NDVISignal {id: $id})
    SET ns.ndvi = $ndvi_value,
        ns.anomaly = $anomaly,
        ns.date = $date,
        ns.region_id = $region_id
    RETURN ns.id AS id
    """
    params = {
        "id": signal_id,
        "ndvi_value": ndvi_value,
        "anomaly": anomaly,
        "date": date,
        "region_id": region_id,
    }
    result = await neo4j_client.execute_write(query, params)
    return result[0] if result else {"id": signal_id}


def make_data_source_id(name: str) -> str:
    """Generate a deterministic DataSource ID."""
    return f"datasource_{name.lower().replace(' ', '_').replace('/', '_')}"


# ── Relationship reconciliation ────────────────────────────
#
# Idempotent helper that heals the knowledge graph so every signal
# and model-output node is connected to its Region and related nodes.
# Called (a) once as a data repair and (b) automatically after every
# pipeline / model run so newly-ingested nodes stay connected without
# manual intervention.

_REGIME_NAME_TO_ID = {
    "Baseline": "regime_baseline",
    "Drought Onset": "regime_drought_onset",
    "DroughtOnset": "regime_drought_onset",
    "Severe Drought": "regime_severe_drought",
    "SevereDrought": "regime_severe_drought",
    "Flood Watch": "regime_flood_watch",
    "FloodWatch": "regime_flood_watch",
    "Flood Emergency": "regime_flood_emergency",
    "FloodEmergency": "regime_flood_emergency",
}

# Signal node labels that hold a region_id property and should be
# linked to their Region via MEASURED_IN.
_REGION_LINKED_LABELS = [
    "RainfallSignal",
    "FoodPriceSignal",
    "IPCPhaseSignal",
    "NDVISignal",
    "StochasticSignal",
    "BMAScore",
    "ForecastSignal",
    "ConflictSignal",
    "CausalEdge",
    "Alert",
]


async def reconcile_graph_relationships() -> dict:
    """Heal all cross-type relationships in the knowledge graph.

    Idempotent — safe to run repeatedly. Links orphaned signals/model
    outputs to their Region, wires Regions to their HazardRegime, creates
    HAS_HAZARD for elevated-risk regions, connects CausalEdges to their
    source/target signals, and adds PREDICTS from model outputs to the
    rainfall signal they consume.

    Returns a summary dict of the counts of relationships created.
    """
    summary = {}

    # 1. MEASURED_IN — link every region-linked signal/model node to Region
    for label in _REGION_LINKED_LABELS:
        q = f"""
        MATCH (n:{label})
        WHERE n.region_id IS NOT NULL
        MATCH (r:Region {{id: n.region_id}})
        MERGE (n)-[:MEASURED_IN]->(r)
        WITH count(r) AS cnt
        RETURN cnt
        """
        try:
            result = await neo4j_client.execute_write(q)
            summary[f"measured_in_{label}"] = result[0]["cnt"] if result else 0
        except Exception as exc:
            logger.warning("reconcile MEASURED_IN for %s failed: %s", label, exc)

    # 2. IN_REGIME — region -> HazardRegime using current_regime.
    # The stored current_regime may be either a camelCase name
    # ("SevereDrought") or already a regime id ("regime_severe_drought"),
    # so resolve to a canonical HazardRegime id in both cases.
    regions_result = await neo4j_client.execute_read(
        "MATCH (r:Region) RETURN r.id AS id, r.current_regime AS regime"
    )
    in_regime_count = 0
    for row in regions_result:
        regime_val = str(row.get("regime") or "").strip()
        if not regime_val:
            continue
        # If it's already a regime id, use it directly; otherwise map the
        # camelCase/"Drought Onset" style name to the canonical id.
        if regime_val.startswith("regime_"):
            regime_id = regime_val
        else:
            regime_id = _REGIME_NAME_TO_ID.get(regime_val)
        if not regime_id:
            continue
        # MERGE the HazardRegime node by id so IN_REGIME is created even if
        # the regime node is missing (e.g. pristine migration state where
        # only some regime nodes exist). Self-healing and idempotent.
        in_result = await neo4j_client.execute_write(
            """
            MATCH (r:Region {id: $rid})
            MERGE (hr:HazardRegime {id: $hid})
            SET hr.name = COALESCE(hr.name, $regime_name)
            MERGE (r)-[:IN_REGIME]->(hr)
            WITH count(hr) AS cnt
            RETURN cnt
            """,
            {"rid": row["id"], "hid": regime_id, "regime_name": regime_val},
        )
        in_regime_count += in_result[0]["cnt"] if in_result else 0
    summary["in_regime"] = in_regime_count

    # 3. HAS_HAZARD — elevated-risk regions get drought/flood hazard
    q = """
    MATCH (r:Region)
    WHERE r.current_risk_score >= 40
    MATCH (h:HazardType {id: 'hazard_drought'})
    MERGE (r)-[:HAS_HAZARD]->(h)
    WITH count(h) AS cnt
    RETURN cnt
    """
    result = await neo4j_client.execute_write(q)
    summary["has_hazard_drought"] = result[0]["cnt"] if result else 0

    q = """
    MATCH (r:Region)
    WHERE r.current_regime CONTAINS 'Flood'
    MATCH (h:HazardType {id: 'hazard_flood'})
    MERGE (r)-[:HAS_HAZARD]->(h)
    WITH count(h) AS cnt
    RETURN cnt
    """
    result = await neo4j_client.execute_write(q)
    summary["has_hazard_flood"] = result[0]["cnt"] if result else 0

    # 4. CAUSES — connect CausalEdges to their source/target signal nodes
    causal_result = await neo4j_client.execute_read(
        """
        MATCH (e:CausalEdge)
        WHERE e.active IS NULL OR e.active = true
        RETURN e.id AS id, e.region_id AS region_id,
               e.source_variable AS src, e.target_variable AS tgt
        """
    )
    causes_count = 0
    for row in causal_result:
        source_signal = await _resolve_signal_for_var(row.get("region_id"), row.get("src"))
        target_signal = await _resolve_signal_for_var(row.get("region_id"), row.get("tgt"))
        if source_signal and target_signal:
            await neo4j_client.execute_write(
                """
                MATCH (s {id: $src_id})
                MATCH (e:CausalEdge {id: $edge_id})
                MATCH (t {id: $tgt_id})
                MERGE (s)-[:CAUSES]->(e)
                MERGE (e)-[:CAUSES]->(t)
                """,
                {"src_id": source_signal, "edge_id": row["id"], "tgt_id": target_signal},
            )
            causes_count += 1
    summary["causes"] = causes_count

    # 5. PREDICTS — model outputs predict the rainfall signal they consume
    q = """
    MATCH (n:StochasticSignal)
    WHERE n.region_id IS NOT NULL
    MATCH (rs:RainfallSignal {region_id: n.region_id})
    WITH n, rs ORDER BY rs.date DESC LIMIT 1
    MERGE (n)-[:PREDICTS]->(rs)
    WITH count(rs) AS cnt
    RETURN cnt
    """
    result = await neo4j_client.execute_write(q)
    summary["predicts_stochastic"] = result[0]["cnt"] if result else 0

    q = """
    MATCH (n:BMAScore)
    WHERE n.region_id IS NOT NULL
    MATCH (rs:RainfallSignal {region_id: n.region_id})
    WITH n, rs ORDER BY rs.date DESC LIMIT 1
    MERGE (n)-[:PREDICTS]->(rs)
    WITH count(rs) AS cnt
    RETURN cnt
    """
    result = await neo4j_client.execute_write(q)
    summary["predicts_bma"] = result[0]["cnt"] if result else 0

    logger.info("Graph reconciliation complete: %s", summary)
    return summary


async def _resolve_signal_for_var(region_id: str, var: str):
    """Return the id of the most recent signal node for a variable.

    Maps a VARLiNGAM variable name (e.g. 'spi_30d', 'ipc_phase') to the
    matching signal node label + property, then returns the most recent
    node id for that region. Returns None if no mapping or no node found.
    """
    if not region_id or not var:
        return None

    # variable → (label, property)
    mapping = {
        "spi_30d": ("RainfallSignal", "spi_30d"),
        "spi": ("RainfallSignal", "spi_30d"),
        "ipc_phase": ("IPCPhaseSignal", "phase"),
        "ipc": ("IPCPhaseSignal", "phase"),
        "food_price": ("FoodPriceSignal", "price_usd"),
        "price": ("FoodPriceSignal", "price_usd"),
        "ndvi": ("NDVISignal", "ndvi"),
    }
    mapped = mapping.get(str(var).strip().lower())
    if not mapped:
        return None
    label, prop = mapped

    rows = await neo4j_client.execute_read(
        f"""
        MATCH (n:{label})
        WHERE n.region_id = $region_id AND n.{prop} IS NOT NULL
        RETURN n.id AS id
        ORDER BY n.date DESC LIMIT 1
        """,
        {"region_id": region_id},
    )
    return rows[0]["id"] if rows else None
