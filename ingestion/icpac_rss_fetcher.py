"""HazardGraph — ICPAC RSS feed ingestion with Groq LLM extraction.

Fetches https://www.icpac.net/feed/, parses RSS entries, uses
Groq llama-3.3-70b-versatile to extract structured hazard fields,
and writes ForecastSignal nodes to Neo4j with DataSource lineage.
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx
from groq import AsyncGroq
from pydantic import BaseModel, Field

from config.settings import settings
from db.neo4j_client import neo4j_client
from graph.node_writers import (
    upsert_forecast_signal,
    link_signal_to_region,
    upsert_data_source,
    make_signal_id,
    make_data_source_id,
)
from graph.lineage import record_lineage, update_data_source_stats

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────
# The /feed/ path returns 404; the working WordPress RSS2 endpoint is ?feed=rss2
ICPAC_RSS_URL = "https://www.icpac.net/?feed=rss2"
ICPAC_SOURCE_NAME = "ICPAC RSS Feed"
ICPAC_SOURCE_ID = make_data_source_id(ICPAC_SOURCE_NAME)

MAX_RETRIES = 3
BASE_DELAY_S = 2.0  # exponential backoff base

# ── Pydantic model for Groq structured output ──────────────


class ExtractedHazardInfo(BaseModel):
    """Structured fields extracted from an ICPAC news article by Groq."""
    region: str = Field(description="The East African region/country mentioned (e.g. Kenya, Somalia, Ethiopia)")
    hazard_type: str = Field(description="The hazard type: drought, flood, locust, conflict, heatwave, disease_outbreak, storm, landslide, frost, wildfire, market_shock")
    severity: float = Field(description="Severity score 0.0 to 1.0", ge=0.0, le=1.0)
    forecast_horizon_days: int = Field(description="Forecast horizon in days (0 if current/nowcast)")
    confidence_pct: float = Field(description="Confidence percentage 0.0 to 100.0", ge=0.0, le=100.0)


# ── Retry decorator ────────────────────────────────────────


async def _retry_async(func, *args, **kwargs):
    """Execute an async call with exponential backoff retry."""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                delay = BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning(
                    "Attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                    attempt, MAX_RETRIES, func.__name__, exc, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "All %d attempts failed for %s: %s",
                    MAX_RETRIES, func.__name__, exc,
                )
    raise last_exc


# ── RSS Fetching ───────────────────────────────────────────


async def fetch_rss_feed() -> list[dict]:
    """Fetch and parse the ICPAC RSS feed.

    Returns a list of entry dicts with title, published, summary, link.
    """
    async def _fetch():
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(ICPAC_RSS_URL)
            response.raise_for_status()
            return response.text

    xml_text = await _retry_async(_fetch)
    feed = feedparser.parse(xml_text)

    entries = []
    for entry in feed.entries:
        entries.append({
            "title": entry.get("title", ""),
            "published": entry.get("published", ""),
            "summary": entry.get("summary", ""),
            "link": entry.get("link", ""),
        })

    logger.info("Fetched %d entries from ICPAC RSS feed", len(entries))
    return entries


# ── Groq LLM Extraction ────────────────────────────────────


async def extract_hazard_info(entry: dict) -> Optional[ExtractedHazardInfo]:
    """Use Groq llama-3.3-70b-versatile to extract structured hazard info.

    Returns None if extraction fails or no hazard info is found.
    """
    client = AsyncGroq(api_key=settings.groq_api_key)

    prompt = (
        "You are a climate early warning analyst. Extract structured hazard information "
        "from the following ICPAC news article. If no hazard is mentioned, return "
        "region='unknown', hazard_type='unknown', severity=0.0, forecast_horizon_days=0, confidence_pct=0.0.\n\n"
        f"Title: {entry['title']}\n"
        f"Published: {entry['published']}\n"
        f"Summary: {entry['summary'][:2000]}\n"
        f"Link: {entry['link']}\n"
    )

    async def _call_groq():
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": "You extract structured hazard early warning data from news articles. "
                               "Respond only with valid JSON matching the requested schema.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=300,
        )
        return response.choices[0].message.content

    try:
        raw = await _retry_async(_call_groq)
        parsed = ExtractedHazardInfo.model_validate_json(raw)
        logger.debug("Extracted: region=%s hazard=%s severity=%.2f", parsed.region, parsed.hazard_type, parsed.severity)
        return parsed
    except Exception as exc:
        logger.warning("Groq extraction failed for entry '%s': %s", entry.get("title", "?"), exc)
        return None


# ── Region ID resolution ───────────────────────────────────


def resolve_region_id(region_name: str) -> Optional[str]:
    """Map a region name from Groq to a Neo4j Region node ID.

    Handles common variations and partial matches.
    """
    if not region_name or region_name.lower() == "unknown":
        return None

    name_lower = region_name.strip().lower()

    # Direct mapping
    region_map = {
        "ethiopia": "region_ethiopia",
        "kenya": "region_kenya",
        "somalia": "region_somalia",
        "sudan": "region_sudan",
        "south sudan": "region_south_sudan",
        "uganda": "region_uganda",
        "djibouti": "region_djibouti",
        "eritrea": "region_eritrea",
        "tanzania": "region_tanzania",
        "burundi": "region_burundi",
        "rwanda": "region_rwanda",
        "east africa": None,  # too broad
        "igad": None,
    }

    return region_map.get(name_lower)


# ── Main ingestion pipeline ────────────────────────────────


async def ingest_icpac_rss() -> dict:
    """Main ingestion pipeline: fetch RSS → extract with Groq → write to Neo4j.

    Returns a summary dict with counts of processed entries.
    """
    summary = {
        "total_entries": 0,
        "processed": 0,
        "skipped": 0,
        "errors": 0,
        "source_id": ICPAC_SOURCE_ID,
    }

    try:
        # 1. Ensure DataSource node exists
        await upsert_data_source(
            source_id=ICPAC_SOURCE_ID,
            name=ICPAC_SOURCE_NAME,
            url=ICPAC_RSS_URL,
        )

        # 2. Fetch RSS entries
        entries = await fetch_rss_feed()
        summary["total_entries"] = len(entries)

        if not entries:
            logger.info("No entries found in ICPAC RSS feed")
            return summary

        # 3. Process each entry
        for entry in entries:
            try:
                # Extract hazard info via Groq
                info = await extract_hazard_info(entry)
                if info is None or info.hazard_type == "unknown":
                    summary["skipped"] += 1
                    continue

                # Generate deterministic signal ID
                date_str = entry.get("published", datetime.now(timezone.utc).isoformat())
                signal_id = make_signal_id("icpac", info.hazard_type, date_str)

                # Write ForecastSignal to Neo4j
                await upsert_forecast_signal(
                    signal_id=signal_id,
                    hazard_type=info.hazard_type,
                    severity=info.severity,
                    horizon_days=info.forecast_horizon_days,
                    confidence_pct=info.confidence_pct,
                )

                # Link to region if resolvable
                region_id = resolve_region_id(info.region)
                if region_id:
                    await link_signal_to_region(signal_id, region_id)

                # Record lineage
                await record_lineage(signal_id, ICPAC_SOURCE_ID)

                summary["processed"] += 1
                logger.info(
                    "Processed entry: hazard=%s region=%s severity=%.2f",
                    info.hazard_type, info.region, info.severity,
                )

            except Exception as exc:
                summary["errors"] += 1
                logger.error("Failed to process entry '%s': %s", entry.get("title", "?"), exc)
                continue

        # 4. Update DataSource stats
        await update_data_source_stats(
            source_id=ICPAC_SOURCE_ID,
            record_count=summary["processed"],
            hash_value=hashlib.sha256(str(entries).encode()).hexdigest()[:32],
        )

    except Exception as exc:
        summary["errors"] += 1
        logger.error("ICPAC RSS ingestion pipeline failed: %s", exc)

    logger.info(
        "ICPAC RSS ingestion complete: %d processed, %d skipped, %d errors out of %d entries",
        summary["processed"], summary["skipped"], summary["errors"], summary["total_entries"],
    )
    return summary