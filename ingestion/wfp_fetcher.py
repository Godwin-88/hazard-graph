"""HazardGraph — WFP DataBridges v2 food price data fetcher.

Fetches food price data for IGAD countries from the WFP DataBridges
API Gateway v2 (https://gateway.api.wfp.org/vam-data-bridges/v2).

The legacy VAM API (api.vam.wfp.org) was deprecated. The new API
requires OAuth2 client credentials flow. Register at:
  https://databridges.vam.wfp.org → Profile → API Key section

Writes FoodPriceSignal nodes to Neo4j and auto-creates alerts for
price spikes (>30% change in 30d).
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
from db.postgres_client import async_session_factory
from db.redis_client import redis_client
from graph.node_writers import upsert_food_price_signal, upsert_data_source, make_data_source_id
from graph.lineage import record_lineage, update_data_source_stats
from models.postgres.alerts import Alert, AlertStatus

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────
SOURCE_NAME = "WFP DataBridges v2 Food Prices"
SOURCE_ID = make_data_source_id(SOURCE_NAME)
WFP_GATEWAY_BASE = "https://gateway.api.wfp.org/vam-data-bridges/v2"
WFP_TOKEN_URL = "https://api.wfp.org/token"

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

# DataBridges CountryCode (same values as legacy adm0Code)
ADM0_CODES = {
    "ETH": 231, "KEN": 114, "SOM": 184, "SDN": 191, "SSD": 225,
    "UGA": 218, "DJI": 49,  "ERI": 67,  "TZA": 213, "BDI": 28,  "RWA": 182,
}

# Commodities to fetch (ID → name)
COMMODITIES = {15: "Maize", 83: "Sorghum", 2: "Wheat"}

MAX_RETRIES = 3
BASE_DELAY_S = 2.0


# ── Date normalisation helper ─────────────────────────────


def _normalise_date(raw_date) -> str:
    """Normalise a DataBridges date value to YYYY-MM-DD.

    Handles ISO datetime strings, YYYY-MM, YYYY, and numeric YYYYMM.
    Returns a safe default if the value cannot be parsed.
    """
    if raw_date is None:
        return "2024-01-01"

    s = str(raw_date).strip()
    if not s:
        return "2024-01-01"

    # Numeric YYYYMM (e.g. 202608) or YYYY (e.g. 2026)
    if s.isdigit():
        if len(s) == 8:
            return f"{s[:4]}-{s[4:6]}-01"
        if len(s) == 4:
            return f"{s}-01-01"
        # Could be a Unix timestamp — fall back to safe default
        return "2024-01-01"

    # ISO datetime or date string — take the first 10 chars (YYYY-MM-DD)
    candidate = s[:10]
    # Validate the candidate is a plausible date
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
        return candidate
    except ValueError:
        pass

    # YYYY-MM only
    if len(s) >= 7:
        try:
            datetime.strptime(s[:7], "%Y-%m")
            return f"{s[:7]}-01"
        except ValueError:
            pass

    # YYYY only
    if len(s) >= 4 and s[:4].isdigit():
        return f"{s[:4]}-01-01"

    return "2024-01-01"


# ── OAuth2 Token Manager ──────────────────────────────────


class WFPTokenManager:
    """Caches and auto-refreshes the OAuth2 bearer token."""

    def __init__(self):
        self._token: Optional[str] = None
        self._expires_at: datetime = datetime.min

    async def get_token(self) -> Optional[str]:
        """Return a valid bearer token, refreshing if expired."""
        if datetime.utcnow() < self._expires_at - timedelta(seconds=60):
            return self._token

        client_id = settings.wfp_client_id
        client_secret = settings.wfp_client_secret
        if not client_id or not client_secret:
            logger.warning("WFP DataBridges credentials not configured in .env")
            return None

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    WFP_TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": "api://wfp-api-mediation-service/.default",
                    },
                )
                resp.raise_for_status()
                payload = resp.json()
                self._token = payload["access_token"]
                self._expires_at = datetime.utcnow() + timedelta(
                    seconds=payload.get("expires_in", 3600)
                )
                logger.info("WFP DataBridges OAuth token refreshed.")
                return self._token
        except Exception as exc:
            logger.error("WFP OAuth token refresh failed: %s", exc)
            return None


_token_mgr = WFPTokenManager()


# ── DataBridges API Client ────────────────────────────────


async def _fetch_price_monthly(
    adm0_code: int,
    commodity_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """Fetch monthly commodity prices from DataBridges PriceMonthly endpoint.

    Handles pagination automatically. Returns all price records.
    """
    token = await _token_mgr.get_token()
    if not token:
        logger.warning("No WFP token available — skipping DataBridges fetch")
        return []

    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "CountryCode": adm0_code,
        "CommodityID": commodity_id,
        "format": "json",
        "page": 1,
    }
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date

    url = f"{WFP_GATEWAY_BASE}/MarketPrices/PriceMonthly"
    all_results: list[dict] = []

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    resp = await client.get(url, headers=headers, params=params)
                    resp.raise_for_status()
                    break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        # Token may have expired — force refresh and retry
                        logger.warning("WFP token expired, refreshing...")
                        self = _token_mgr  # reset token
                        self._token = None
                        self._expires_at = datetime.min
                        new_token = await _token_mgr.get_token()
                        if new_token:
                            headers["Authorization"] = f"Bearer {new_token}"
                            continue
                    if attempt < MAX_RETRIES:
                        delay = BASE_DELAY_S * (2 ** (attempt - 1))
                        logger.warning(
                            "WFP DataBridges error %s, attempt %d/%d: %s. Retry in %.1fs",
                            url, attempt, MAX_RETRIES, e, delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "WFP DataBridges failed after %d attempts: %s",
                            MAX_RETRIES, e,
                        )
                        return all_results
                except Exception as exc:
                    logger.error("WFP DataBridges request error: %s", exc)
                    return all_results

            data = resp.json()
            # DataBridges returns {"items": [...], "page": N, "totalItems": N}
            items = data.get("items", [])
            all_results.extend(items)

            total = data.get("totalItems", len(items))
            fetched = (params["page"] - 1) * max(len(items), 1) + len(items)
            if fetched >= total or not items:
                break
            params["page"] += 1

    logger.info(
        "WFP PriceMonthly: fetched %d records (adm0=%d, commodity=%d)",
        len(all_results), adm0_code, commodity_id,
    )
    return all_results


async def fetch_country_prices(iso3: str) -> list[dict]:
    """Fetch food prices for a single country across all commodities.

    Uses the DataBridges v2 PriceMonthly endpoint with OAuth2.
    Returns list of price data dicts compatible with the existing schema.
    """
    region_id = IGAD_COUNTRIES.get(iso3)
    adm0 = ADM0_CODES.get(iso3)
    if not region_id or not adm0:
        logger.warning("Unknown ISO3 code: %s", iso3)
        return []

    results = []

    for commodity_id, commodity_name in COMMODITIES.items():
        price_points = await _fetch_price_monthly(adm0, commodity_id)

        if not price_points:
            logger.info("No price data for %s / %s", iso3, commodity_name)
            continue

        # Sort by date descending, take most recent two
        sorted_prices = sorted(
            price_points,
            key=lambda x: x.get("date", x.get("mpDate", x.get("mpYear", 0))),
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

        # DataBridges field names: mpPrice, mpDate, marketName, etc.
        price_usd = current.get("mpPrice", current.get("price", 0))
        prev_price = previous.get("mpPrice", previous.get("price", 0)) if previous else price_usd

        market = current.get("marketName", current.get("market", "unknown"))
        # Date format: "YYYY-MM-DD" or "YYYY-MM" or "YYYY" or timestamp
        raw_date = current.get("mpDate", current.get("date", current.get("mpYear", "2024")))
        # Normalise to YYYY-MM-DD safely
        date_str = _normalise_date(raw_date)

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

        logger.info(
            "WFP DataBridges %s / %s: $%.2f (%+.1f%% 30d) at %s",
            iso3, commodity_name, float(price_usd), pct_change_30d, market,
        )

    return results


async def fetch_all_countries() -> dict:
    """Fetch WFP DataBridges prices for all IGAD countries.

    Returns summary dict with counts.
    """
    summary = {
        "total_countries": 0,
        "total_signals": 0,
        "price_spikes": 0,
        "alerts_created": 0,
        "errors": 0,
        "source_id": SOURCE_ID,
    }

    try:
        # Ensure DataSource node exists
        await upsert_data_source(
            source_id=SOURCE_ID,
            name=SOURCE_NAME,
            url=f"{WFP_GATEWAY_BASE}/MarketPrices/PriceMonthly",
        )

        for iso3 in IGAD_COUNTRIES:
            summary["total_countries"] += 1
            cache_key = f"wfp:{iso3}"

            # Check cache
            try:
                cached = await redis_client.get(cache_key)
            except Exception as exc:
                logger.warning("Redis cache read failed for %s: %s", cache_key, exc)
                cached = None

            try:
                if cached:
                    try:
                        prices = json.loads(cached)
                    except Exception:
                        prices = await fetch_country_prices(iso3)
                else:
                    prices = await fetch_country_prices(iso3)
            except Exception as exc:
                summary["errors"] += 1
                logger.error("WFP fetch failed for %s: %s", iso3, exc)
                continue

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
                    signal_id = (
                        f"foodprice_{price_data['region_id']}"
                        f"_{price_data['commodity']}_{price_data['date']}"
                    ).replace(" ", "_")

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
                                logger.info(
                                    "Price spike alert created for %s: %s %+.1f%%",
                                    price_data["region_id"], price_data["commodity"],
                                    price_data["pct_change_30d"],
                                )
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
        logger.error("WFP DataBridges fetch_all_countries failed: %s", exc)
        summary["errors"] += 1

    logger.info(
        "WFP DataBridges ingestion complete: %d signals, %d price spikes, "
        "%d alerts from %d countries",
        summary["total_signals"], summary["price_spikes"],
        summary["alerts_created"], summary["total_countries"],
    )
    return summary