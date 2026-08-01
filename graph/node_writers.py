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
