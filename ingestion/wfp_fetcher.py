"""HazardGraph — WFP VAM food price data fetcher.

Fetches food price data for IGAD countries from the WFP VAM API.
Writes FoodPriceSignal nodes to Neo4j and auto-creates alerts for
price spikes (IPC phase ≥ 3 indicator: >30% change in 30d).
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from config.settings import settings
from db.neo4j_client import neo4j_client
from db.postgres_client import async_session_factory
from db.redis_client import redis_client
from graph.node_writers import upsert_food_price_signal, upsert_data_source, make_data_source_id
from graph.lineage import record_lineage, update_data_source_stats
from models.postgres.alerts import Alert, AlertStatus

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────
SOURCE_NAME = "WFP VAM Food Prices"
SOURCE_ID = make_data_source_id(SOURCE_NAME)
WFP_BASE_URL = "https://api.vam.wfp.org"

# ISO3 codes for IGAD countries
IGAD_COUNTRIES = {
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

# Admin0 codes for WFP API
ADM0_CODES = {
    "ETH": 231, "KEN": 114, "SOM": 184, "SDN": 191, "SSD": 225,
    "UGA": 218, "DJI": 49,  "ERI": 67,  "TZA": 213, "BDI": 28,  "RWA": 182,
}

# Commodities to fetch (ID → name)
COMMODITIES = {15: "Maize", 83: "Sorghum", 2: "Wheat"}

MAX_RETRIES = 3
BASE_DELAY_S = 2.0


async def _wfp_get(endpoint: str, params: dict = None, timeout: int = 30) -> Optional[dict]:
    """Make an async GET request to the WFP VAM API with retry logic."""
    url = f"{WFP_BASE_URL}{endpoint}"

    async def _fetch():
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await _fetch()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                delay = BASE_DELAY_S * (2 ** attempt)
                logger.warning("WFP API rate limited. Retrying in %.1fs...", delay)
                await asyncio.sleep(delay)
                continue
            if attempt < MAX_RETRIES:
                delay = BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning("WFP API error %s, attempt %d/%d: %s. Retry in %.1fs", url, attempt, MAX_RETRIES, exc, delay)
                await asyncio.sleep(delay)
            else:
                logger.error("WFP API failed after %d attempts: %s", MAX_RETRIES, exc)
                return None
        except Exception as exc:
            logger.error("WFP API request error: %s", exc)
            return None
    return None


async def fetch_country_prices(iso3: str) -> list[dict]:
    """Fetch food prices for a single country across all commodities.

    Returns list of price data dicts.
    """
    region_id = IGAD_COUNTRIES.get(iso3)
    adm0 = ADM0_CODES.get(iso3)
    if not region_id or not adm0:
        logger.warning("Unknown ISO3 code: %s", iso3)
        return []

    results = []

    for commodity_id, commodity_name in COMMODITIES.items():
        # Get price series for this commodity
        endpoint = f"/PriceSeries/GetPriceSeries"
        params = {"adm0Code": adm0, "commodityID": commodity_id}

        data = await _wfp_get(endpoint, params)

        if not data:
            logger.warning("No price data for %s / %s", iso3, commodity_name)
            continue

        # Parse the response — WFP returns a list of price points
        price_points = data if isinstance(data, list) else data.get("data", [])

        if not price_points:
            logger.info("No price points for %s / %s", iso3, commodity_name)
            continue

        # Sort by date descending, take most recent two
        sorted_prices = sorted(
            price_points,
            key=lambda x: x.get("date", x.get("mp_year", 0)),
            reverse=True,
        )

        if len(sorted_prices) >= 2:
            current = sorted_prices[0]
            previous = sorted_prices[1]
        elif len(sorted_prices) == 1:
            current = sorted_prices[0]
            previous = None
        else:
            continue

        price_usd = current.get("mp_price", current.get("price", 0))
        prev_price = previous.get("mp_price", previous.get("price", 0)) if previous else price_usd

        # Get market name
        market = current.get("market_name", current.get("market", "unknown"))
        date_str = str(current.get("date", current.get("mp_year", "2024")))

        pct_change_30d = 0.0
        if prev_price > 0:
            pct_change_30d = ((price_usd - prev_price) / prev_price) * 100

        results.append({
            "region_id": region_id,
            "iso3": iso3,
            "commodity": commodity_name,
            "market": market,
            "price_usd": float(price_usd),
            "pct_change_30d": round(pct_change_30d, 2),
            "date": date_str,
        })

        logger.info("WFP %s / %s: $%.2f (%+.1f%% 30d) at %s", iso3, commodity_name, float(price_usd), pct_change_30d, market)

    return results


async def fetch_all_countries() -> dict:
    """Fetch WFP prices for all IGAD countries.

    Returns summary dict with counts.
    """
    summary = {"total_countries": 0, "total_signals": 0, "price_spikes": 0, "alerts_created": 0, "errors": 0, "source_id": SOURCE_ID}

    try:
        # Ensure DataSource node exists
        await upsert_data_source(
            source_id=SOURCE_ID,
            name=SOURCE_NAME,
            url=WFP_BASE_URL + "/Markets/GeoJSONQuery",
        )

        for iso3 in IGAD_COUNTRIES:
            summary["total_countries"] += 1
            cache_key = f"wfp:{iso3}"

            # Check cache
            cached = await redis_client.get(cache_key)
            if cached:
                try:
                    prices = json.loads(cached)
                except Exception:
                    prices = await fetch_country_prices(iso3)
            else:
                prices = await fetch_country_prices(iso3)

            if not prices:
                continue

            # Cache for 24h
            try:
                await redis_client.set(cache_key, json.dumps(prices), ttl=86400)
            except Exception as exc:
                logger.warning("Redis cache set failed for %s: %s", cache_key, exc)

            for price_data in prices:
                try:
                    # Generate deterministic signal ID
                    signal_id = f"foodprice_{price_data['region_id']}_{price_data['commodity']}_{price_data['date']}".replace(" ", "_")

                    await upsert_food_price_signal(
                        signal_id=signal_id,
                        commodity=price_data["commodity"],
                        market=price_data["market"],
                        price_usd=price_data["price_usd"],
                        pct_change_30d=price_data["pct_change_30d"],
                        date=price_data["date"],
                        region_id=price_data["region_id"],
                    )

                    # Create MEASURED_IN relationship
                    await neo4j_client.execute_write(
                        """
                        MATCH (fps:FoodPriceSignal {id: $signal_id})
                        MATCH (r:Region {id: $region_id})
                        MERGE (fps)-[:MEASURED_IN]->(r)
                        """,
                        {"signal_id": signal_id, "region_id": price_data["region_id"]},
                    )

                    # Record lineage
                    await record_lineage(signal_id, SOURCE_ID)

                    summary["total_signals"] += 1

                    # Check for price spike (>30% in 30d)
                    if price_data["pct_change_30d"] > 30.0:
                        summary["price_spikes"] += 1
                        # Write alert to PostgreSQL
                        try:
                            async with async_session_factory() as session:
                                alert = Alert(
                                    region_id=price_data["region_id"],
                                    language="en",
                                    message_text=(
                                        f"PRICE SPIKE: {price_data['commodity']} in {price_data['market']} "
                                        f"({price_data['iso3']}) increased {price_data['pct_change_30d']:+.1f}% "
                                        f"in 30 days. Current price: ${price_data['price_usd']:.2f}"
                                    ),
                                    risk_score_at_trigger=min(price_data["pct_change_30d"] / 100, 1.0),
                                    generated_at=datetime.now(timezone.utc),
                                    status=AlertStatus.PENDING,
                                    kelly_priority=min(price_data["pct_change_30d"] / 100, 1.0),
                                )
                                session.add(alert)
                                await session.commit()
                                summary["alerts_created"] += 1
                                logger.info("Price spike alert created for %s: %s %+.1f%%", price_data["region_id"], price_data["commodity"], price_data["pct_change_30d"])
                        except Exception as exc:
                            logger.error("Failed to create alert for price spike: %s", exc)

                except Exception as exc:
                    summary["errors"] += 1
                    logger.error("Failed to process WFP signal for %s: %s", iso3, exc)

        # Update DataSource stats
        await update_data_source_stats(
            source_id=SOURCE_ID,
            record_count=summary["total_signals"],
            hash_value=hashlib.sha256(str(summary).encode()).hexdigest()[:32],
        )

    except Exception as exc:
        logger.error("WFP fetch_all_countries failed: %s", exc)
        summary["errors"] += 1

    logger.info(
        "WFP ingestion complete: %d signals, %d price spikes, %d alerts from %d countries",
        summary["total_signals"], summary["price_spikes"], summary["alerts_created"], summary["total_countries"],
    )
    return summary