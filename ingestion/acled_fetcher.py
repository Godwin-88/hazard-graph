"""HazardGraph — ACLED conflict data fetcher.

Fetches conflict events from the ACLED API (free account, instant access)
for IGAD countries. Aggregates events per week per region and writes
ConflictSignal nodes to Neo4j with DataSource lineage.

Uses the OAuth token flow:
  1. POST to https://acleddata.com/oauth/token with email/password
  2. Receive access_token (24h) + refresh_token (14d)
  3. Send `Authorization: Bearer <token>` on data requests

Requires ACLED_EMAIL and ACLED_PASSWORD in .env (register free at
https://acleddata.com).
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from config.settings import settings
from db.neo4j_client import neo4j_client
from db.redis_client import redis_client
from graph.node_writers import (
    upsert_conflict_signal,
    upsert_data_source,
    make_data_source_id,
)
from graph.lineage import record_lineage, update_data_source_stats

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────
SOURCE_NAME = "ACLED Conflict Events"
SOURCE_ID = make_data_source_id(SOURCE_NAME)

MAX_RETRIES = 3
BASE_DELAY_S = 2.0

# Redis key for caching the OAuth access token
ACLED_TOKEN_CACHE_KEY = "acled:access_token"

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


async def _get_access_token() -> Optional[str]:
    """Obtain an ACLED OAuth access token, caching it in Redis.

    Returns the bearer token string, or None on failure.
    """
    # 1. Try cached token first
    if redis_client:
        try:
            cached = await redis_client.get(ACLED_TOKEN_CACHE_KEY)
            if cached:
                logger.debug("Using cached ACLED access token")
                return cached
        except Exception as exc:
            logger.warning("Failed to read cached ACLED token: %s", exc)

    # 2. Request a fresh token
    email = settings.acled_email
    password = settings.acled_password
    if not email or not password:
        logger.warning("ACLED credentials missing — set ACLED_EMAIL/ACLED_PASSWORD in .env")
        return None

    payload = {
        "username": email,
        "password": password,
        "grant_type": "password",
        "client_id": "acled",
        "scope": "authenticated",
    }

    async def _request_token():
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.post(
                settings.acled_token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            token_data = await _request_token()
            token = token_data.get("access_token")
            if not token:
                logger.error("ACLED token response missing access_token: %s", token_data)
                return None

            # Cache token (expires_in is 86400s = 24h; cache for 23h to be safe)
            if redis_client:
                try:
                    await redis_client.set(
                        ACLED_TOKEN_CACHE_KEY,
                        token,
                        ttl=token_data.get("expires_in", 86400) - 3600,
                    )
                except Exception as exc:
                    logger.warning("Failed to cache ACLED token: %s", exc)

            logger.info("ACLED OAuth token obtained successfully")
            return token

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 401, 403):
                logger.error(
                    "ACLED OAuth auth failed (check ACLED_EMAIL/ACLED_PASSWORD in .env): %s",
                    exc.response.text[:300],
                )
                return None
            if attempt < MAX_RETRIES:
                delay = BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning("ACLED token attempt %d/%d failed: %s. Retry in %.1fs", attempt, MAX_RETRIES, exc, delay)
                await asyncio.sleep(delay)
            else:
                logger.error("ACLED token request failed after %d attempts: %s", MAX_RETRIES, exc)
                return None
        except Exception as exc:
            logger.error("ACLED token request error: %s", exc)
            return None
    return None


async def _fetch_conflict_events(
    token: str,
    country: str,
    start_date: str,
    end_date: str,
) -> Optional[list]:
    """Fetch conflict events for a set of countries from ACLED using Bearer auth."""
    params = {
        "country": country,
        "event_date": f"{start_date}|{end_date}",
        "event_date_where": "BETWEEN",
        "limit": 5000,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async def _fetch():
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(settings.acled_base_url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("data", data if isinstance(data, list) else [])

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await _fetch()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                # Token may have expired — invalidate cache and try once more
                logger.warning("ACLED data request unauthorized — invalidating cached token")
                if redis_client:
                    try:
                        await redis_client.delete(ACLED_TOKEN_CACHE_KEY)
                    except Exception:
                        pass
                if attempt == 1:
                    # Retry once with a fresh token
                    new_token = await _get_access_token()
                    if new_token:
                        headers["Authorization"] = f"Bearer {new_token}"
                        continue
                logger.error("ACLED auth failed — check ACLED_EMAIL/ACLED_PASSWORD in .env")
                return None
            if attempt < MAX_RETRIES:
                delay = BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning("ACLED attempt %d/%d failed: %s. Retry in %.1fs", attempt, MAX_RETRIES, exc, delay)
                await asyncio.sleep(delay)
            else:
                logger.error("ACLED failed after %d attempts: %s", MAX_RETRIES, exc)
                return None
        except Exception as exc:
            logger.error("ACLED request error: %s", exc)
            return None
    return None


async def _aggregate_and_write(events: list, year_week: str, source_suffix: str = "weekly") -> dict:
    """Aggregate conflict events by region and write ConflictSignal nodes.

    Returns counts dict.
    """
    from collections import defaultdict

    # event_country is ISO2; map via a small lookup
    iso2_to_region = {
        "ET": "region_ethiopia",
        "KE": "region_kenya",
        "SO": "region_somalia",
        "SD": "region_sudan",
        "SS": "region_south_sudan",
        "UG": "region_uganda",
        "DJ": "region_djibouti",
        "ER": "region_eritrea",
        "TZ": "region_tanzania",
        "BI": "region_burundi",
        "RW": "region_rwanda",
    }

    by_region = defaultdict(lambda: {"count": 0, "fatalities": 0})
    for ev in events:
        iso2 = (ev.get("iso") or ev.get("country") or "").upper()
        region_id = iso2_to_region.get(iso2[:2])
        if not region_id:
            continue
        by_region[region_id]["count"] += 1
        try:
            by_region[region_id]["fatalities"] += int(ev.get("fatalities") or 0)
        except (TypeError, ValueError):
            pass

    written = 0
    for region_id, agg in by_region.items():
        signal_id = f"conflict_{region_id}_{year_week}"
        await upsert_conflict_signal(
            signal_id=signal_id,
            events_count=agg["count"],
            fatalities=agg["fatalities"],
            event_type="all_conflict",
            location="",
            event_date=year_week,
            region_id=region_id,
        )
        # Create MEASURED_IN relationship
        await neo4j_client.execute_write(
            """
            MATCH (cs:ConflictSignal {id: $signal_id})
            MATCH (r:Region {id: $region_id})
            MERGE (cs)-[:MEASURED_IN]->(r)
            """,
            {"signal_id": signal_id, "region_id": region_id},
        )
        # Record lineage
        await record_lineage(signal_id, SOURCE_ID)
        written += 1

    return {"written": written, "regions_seen": len(by_region)}


async def fetch_conflict_data(lookback_weeks: int = 12) -> dict:
    """Fetch ACLED conflict data for all IGAD countries.

    Returns summary dict with counts.
    """
    summary = {"total": 0, "success": 0, "failed": 0, "source_id": SOURCE_ID}

    if not settings.acled_email or not settings.acled_password:
        logger.warning("ACLED credentials missing — set ACLED_EMAIL/ACLED_PASSWORD in .env")
        return summary

    try:
        await upsert_data_source(
            source_id=SOURCE_ID,
            name=SOURCE_NAME,
            url=settings.acled_base_url,
        )

        # Obtain OAuth token
        token = await _get_access_token()
        if not token:
            summary["failed"] = 1
            return summary

        # Fetch in one request for all IGAD countries
        countries = "|".join(ISO3_TO_REGION.keys())
        end = datetime.now(timezone.utc)
        start = (end - timedelta(weeks=lookback_weeks)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        events = await _fetch_conflict_events(
            token,
            countries,
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )
        if not events:
            summary["failed"] = 1
            return summary

        summary["total"] = len(events)
        week_key = end.isocalendar()
        year_week = f"{week_key[0]}-W{week_key[1]:02d}"

        result = await _aggregate_and_write(events, year_week)
        summary["success"] = result["written"]

        await update_data_source_stats(
            source_id=SOURCE_ID,
            record_count=summary["success"],
            hash_value=hashlib.sha256(str(summary).encode()).hexdigest()[:32],
        )

    except Exception as exc:
        logger.error("ACLED fetch_conflict_data failed: %s", exc)

    logger.info("ACLED ingestion complete: %d events → %d region signals", summary["total"], summary["success"])
    return summary