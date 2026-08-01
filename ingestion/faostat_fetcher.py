"""HazardGraph — FAOSTAT food price fetcher.

Pulls country-level food price indices (maize, sorghum, wheat) from the
FAOSTAT REST API (no key required) for IGAD countries. Writes
FoodPriceSignal nodes to Neo4j with DataSource lineage.
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from db.neo4j_client import neo4j_client
from db.redis_client import redis_client
from graph.node_writers import (
    upsert_food_price_signal,
    upsert_data_source,
    make_data_source_id,
)
from graph.lineage import record_lineage, update_data_source_stats

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────
# Stable base URL (fenixservices.fao.org is legacy/unstable → Cloudflare 521).
# Consumer Price Indices domain code is "CP".
FAOSTAT_BASE_URL = "https://faostatservices.fao.org/api/v1/en/data/CP"
SOURCE_NAME = "FAOSTAT Food Price Indices"
SOURCE_ID = make_data_source_id(SOURCE_NAME)

MAX_RETRIES = 3
BASE_DELAY_S = 2.0

# Split timeouts: fail fast on connect (dead origin → 521), allow longer reads.
FAOSTAT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)

# ISO3 → region_id mapping (matches ipc_fetcher)
ISO3_TO_REGION = {
    "ETH": "region_ethiopia",
    "KEN": "region_kenya",
    "SOM": "region_somalia",
    "SDN": "region_sudan",
    "SSD": "region_south_sudan",
    "UGA": "region_uganda",
    "DJI": "region_djibouti",
    "ERI": "region_eritrea",
    "TZA": "region_tanzania",
    "BDI": "region_burundi",
    "RWA": "region_rwanda",
}

# FAOSTAT item codes: 2511=maize, 2513=sorghum, 2510=wheat (Producer Price Index)
FAOSTAT_ITEMS = {
    "maize": 2511,
    "sorghum": 2513,
    "wheat": 2510,
}


async def _fetch_price_index(country_code: str, item_code: int, year: int) -> Optional[float]:
    """Fetch a single FAOSTAT price index value.

    Returns the latest available index, or None on failure.
    """
    params = {
        "area": country_code,          # ETH, KEN, SOM, SDN
        "element": 5531,               # Producer Price Index
        "year": year,
        "show_code": True,
        "output_type": "objects",      # returns list of dicts
    }

    async def _fetch():
        async with httpx.AsyncClient(timeout=FAOSTAT_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(FAOSTAT_BASE_URL, params=params)
            response.raise_for_status()
            return response.json()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = await _fetch()
            # FAOSTAT returns {"data": [...]} with rows containing "Value"
            rows = data.get("data", []) if isinstance(data, dict) else []
            if not rows:
                return None
            # Take the most recent non-null value
            for row in reversed(rows):
                val = row.get("Value")
                if val is not None and val != "":
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        continue
            return None
        except Exception as exc:
            if attempt < MAX_RETRIES:
                delay = BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning("FAOSTAT attempt %d/%d failed: %s. Retry in %.1fs", attempt, MAX_RETRIES, exc, delay)
                await asyncio.sleep(delay)
            else:
                logger.error("FAOSTAT failed after %d attempts: %s", MAX_RETRIES, exc)
                return None
    return None


async def fetch_all_countries() -> dict:
    """Fetch FAOSTAT price indices for all IGAD countries.

    Returns summary dict with counts.
    """
    summary = {
        "total": 0,
        "total_signals": 0,
        "success": 0,
        "failed": 0,
        "source_id": SOURCE_ID,
    }

    try:
        await upsert_data_source(
            source_id=SOURCE_ID,
            name=SOURCE_NAME,
            url=FAOSTAT_BASE_URL,
        )

        year = datetime.now(timezone.utc).year
        # FAOSTAT publishes with a lag — query a few recent years
        years = list(range(year, year - 3, -1))

        for iso3, region_id in ISO3_TO_REGION.items():
            summary["total"] += 1
            for commodity, item_code in FAOSTAT_ITEMS.items():
                idx = None
                for y in years:
                    idx = await _fetch_price_index(iso3, item_code, y)
                    if idx is not None:
                        break
                if idx is None:
                    summary["failed"] += 1
                    continue

                signal_id = f"food_price_{region_id}_{commodity}_{year}"
                await upsert_food_price_signal(
                    signal_id=signal_id,
                    commodity=commodity,
                    market=f"{region_id} (country-level)",
                    price_usd=idx,
                    pct_change_30d=0.0,
                    date=str(year),
                    region_id=region_id,
                )

                # Create MEASURED_IN relationship
                await neo4j_client.execute_write(
                    """
                    MATCH (fps:FoodPriceSignal {id: $signal_id})
                    MATCH (r:Region {id: $region_id})
                    MERGE (fps)-[:MEASURED_IN]->(r)
                    """,
                    {"signal_id": signal_id, "region_id": region_id},
                )

                # Record lineage
                await record_lineage(signal_id, SOURCE_ID)
                summary["total_signals"] += 1
                summary["success"] += 1

        await update_data_source_stats(
            source_id=SOURCE_ID,
            record_count=summary["success"],
            hash_value=hashlib.sha256(str(summary).encode()).hexdigest()[:32],
        )

    except Exception as exc:
        logger.error("FAOSTAT fetch_all_countries failed: %s", exc)

    logger.info("FAOSTAT ingestion complete: %d signals, %d failed", summary["success"], summary["failed"])
    return summary