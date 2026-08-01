"""HazardGraph — NASA POWER climate data fetcher.

Fetches daily temperature, precipitation, humidity, and wind data from
the NASA POWER API (no key required) for each IGAD region centroid.
Writes RainfallSignal nodes (with climate properties) to Neo4j with
DataSource lineage.
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from config.settings import settings
from db.neo4j_client import neo4j_client
from db.redis_client import redis_client
from graph.node_writers import (
    upsert_rainfall_signal,
    upsert_data_source,
    make_data_source_id,
)
from graph.lineage import record_lineage, update_data_source_stats

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────
POWER_BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
SOURCE_NAME = "NASA POWER Daily Climate"
SOURCE_ID = make_data_source_id(SOURCE_NAME)

MAX_RETRIES = 3
BASE_DELAY_S = 2.0

# Region → centroid lat/lon (derived from COUNTRY_BBOXES in chirps_fetcher)
REGION_CENTROIDS = {
    "region_ethiopia":    {"lat": 9.2,  "lon": 40.5},
    "region_kenya":       {"lat": 0.15, "lon": 38.0},
    "region_somalia":     {"lat": 5.15, "lon": 46.2},
    "region_sudan":       {"lat": 15.45,"lon": 30.4},
    "region_south_sudan": {"lat": 7.85, "lon": 30.05},
    "region_uganda":      {"lat": 1.35, "lon": 32.25},
    "region_djibouti":    {"lat": 11.8, "lon": 42.55},
    "region_eritrea":     {"lat": 15.2, "lon": 39.75},
    "region_tanzania":    {"lat": -6.35,"lon": 34.85},
    "region_burundi":     {"lat": -3.35,"lon": 29.9},
    "region_rwanda":      {"lat": -1.9, "lon": 29.85},
}

# 30-year SPI means/stds per region (reuse from chirps_fetcher)
SPI_PARAMS = {
    "region_ethiopia":   {"mean": 45.0, "std": 22.0},
    "region_kenya":      {"mean": 38.0, "std": 19.0},
    "region_somalia":    {"mean": 18.0, "std": 12.0},
    "region_sudan":      {"mean": 12.0, "std": 8.0},
    "region_south_sudan":{"mean": 55.0, "std": 25.0},
    "region_uganda":     {"mean": 62.0, "std": 28.0},
    "region_djibouti":   {"mean": 8.0,  "std": 6.0},
    "region_eritrea":    {"mean": 15.0, "std": 10.0},
    "region_tanzania":   {"mean": 52.0, "std": 24.0},
    "region_burundi":    {"mean": 70.0, "std": 30.0},
    "region_rwanda":     {"mean": 75.0, "std": 32.0},
}


async def _fetch_power_data(
    lat: float,
    lon: float,
    start: str,
    end: str,
) -> Optional[dict]:
    """Fetch daily climate data from NASA POWER for a point."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start": start,
        "end": end,
        "parameters": "T2M,PRECTOTCORR,RH2M,WS2M",
        "community": "AG",
        "format": "JSON",
    }

    async def _fetch():
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(POWER_BASE_URL, params=params)
            response.raise_for_status()
            return response.json()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await _fetch()
        except Exception as exc:
            if attempt < MAX_RETRIES:
                delay = BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning("NASA POWER attempt %d/%d failed: %s. Retry in %.1fs", attempt, MAX_RETRIES, exc, delay)
                await asyncio.sleep(delay)
            else:
                logger.error("NASA POWER failed after %d attempts: %s", MAX_RETRIES, exc)
                return None
    return None


async def fetch_region_climate(region_id: str, lookback_days: int = 90) -> Optional[dict]:
    """Fetch and process NASA POWER climate for a single region.

    Returns a dict with the latest daily climate values, or None on failure.
    """
    centroid = REGION_CENTROIDS.get(region_id)
    if not centroid:
        logger.warning("Unknown region_id: %s", region_id)
        return None

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    cache_key = f"nasa_power:{region_id}:{start.strftime('%Y%m%d')}:{end.strftime('%Y%m%d')}"
    cached = await redis_client.get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    data = await _fetch_power_data(
        centroid["lat"],
        centroid["lon"],
        start.strftime("%Y%m%d"),
        end.strftime("%Y%m%d"),
    )
    if not data:
        return None

    try:
        properties = data.get("properties", {})
        parameter = properties.get("parameter", {})
        t2m = parameter.get("T2M", {})
        prec = parameter.get("PRECTOTCORR", {})
        rh2m = parameter.get("RH2M", {})
        ws2m = parameter.get("WS2M", {})

        # Get the most recent complete day
        dates = sorted(t2m.keys())
        if not dates:
            return None
        latest = dates[-1]

        temp_c = t2m.get(latest)
        precip_mm = prec.get(latest)
        humidity = rh2m.get(latest)
        wind = ws2m.get(latest)

        if precip_mm is None:
            return None

        # Compute SPI-30 approximation from precipitation
        params = SPI_PARAMS.get(region_id, {"mean": 30.0, "std": 15.0})
        spi = (precip_mm - params["mean"]) / params["std"] if params["std"] > 0 else 0.0
        spi = max(-3.0, min(3.0, spi))
        anomaly_pct = ((precip_mm - params["mean"]) / params["mean"]) * 100 if params["mean"] > 0 else 0.0

        result = {
            "region_id": region_id,
            "date": latest,
            "temperature_c": round(temp_c, 2) if temp_c is not None else None,
            "precip_mm": round(precip_mm, 2),
            "humidity_pct": round(humidity, 2) if humidity is not None else None,
            "wind_ms": round(wind, 2) if wind is not None else None,
            "spi_30d": round(spi, 4),
            "spi_30d_smoothed": round(spi, 4),
            "anomaly_pct": round(anomaly_pct, 2),
            "dekad": latest,
        }

        # Cache in Redis for 6 hours
        try:
            await redis_client.set(cache_key, json.dumps(result), ttl=21600)
        except Exception as exc:
            logger.warning("Redis cache set failed for %s: %s", cache_key, exc)

        return result
    except Exception as exc:
        logger.error("Failed to parse NASA POWER data for %s: %s", region_id, exc)
        return None


async def fetch_all_regions() -> dict:
    """Fetch NASA POWER climate for all 11 IGAD regions.

    Returns summary dict with counts.
    """
    summary = {"total": 0, "success": 0, "failed": 0, "source_id": SOURCE_ID}

    try:
        await upsert_data_source(
            source_id=SOURCE_ID,
            name=SOURCE_NAME,
            url=POWER_BASE_URL,
        )

        for region_id in REGION_CENTROIDS:
            summary["total"] += 1
            try:
                result = await fetch_region_climate(region_id)
                if result is None:
                    summary["failed"] += 1
                    continue

                signal_id = f"rainfall_{region_id}_{result['date']}"
                await upsert_rainfall_signal(
                    signal_id=signal_id,
                    spi_30d=result["spi_30d"],
                    spi_30d_smoothed=result["spi_30d_smoothed"],
                    anomaly_pct=result["anomaly_pct"],
                    dekad=result["dekad"],
                    date=result["date"],
                    region_id=region_id,
                )

                # Add climate properties to the RainfallSignal node
                await neo4j_client.execute_write(
                    """
                    MATCH (rs:RainfallSignal {id: $signal_id})
                    SET rs.temperature_c = $temp,
                        rs.humidity_pct = $humidity,
                        rs.wind_ms = $wind
                    """,
                    {
                        "signal_id": signal_id,
                        "temp": result["temperature_c"],
                        "humidity": result["humidity_pct"],
                        "wind": result["wind_ms"],
                    },
                )

                # Create MEASURED_IN relationship
                await neo4j_client.execute_write(
                    """
                    MATCH (rs:RainfallSignal {id: $signal_id})
                    MATCH (r:Region {id: $region_id})
                    MERGE (rs)-[:MEASURED_IN]->(r)
                    """,
                    {"signal_id": signal_id, "region_id": region_id},
                )

                # Record lineage
                await record_lineage(signal_id, SOURCE_ID)

                summary["success"] += 1
                logger.info("NASA POWER processed %s: temp=%.1fC precip=%.1fmm", region_id, result["temperature_c"] or 0, result["precip_mm"])

            except Exception as exc:
                summary["failed"] += 1
                logger.error("NASA POWER failed for %s: %s", region_id, exc)

        await update_data_source_stats(
            source_id=SOURCE_ID,
            record_count=summary["success"],
            hash_value=hashlib.sha256(str(summary).encode()).hexdigest()[:32],
        )

    except Exception as exc:
        logger.error("NASA POWER fetch_all_regions failed: %s", exc)

    logger.info("NASA POWER ingestion complete: %d success, %d failed out of %d", summary["success"], summary["failed"], summary["total"])
    return summary