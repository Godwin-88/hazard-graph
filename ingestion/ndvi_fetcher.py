"""HazardGraph — NDVI greenness fetcher.

Fetches NDVI vegetation greenness from WFP/HDX datasets (CSV, no API key
needed) and writes NDVISignal nodes to Neo4j with DataSource lineage.
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
from db.redis_client import redis_client
from graph.node_writers import (
    upsert_ndvi_signal,
    upsert_data_source,
    make_data_source_id,
)
from graph.lineage import record_lineage, update_data_source_stats

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────
SOURCE_NAME = "WFP NDVI (HDX)"
SOURCE_ID = make_data_source_id(SOURCE_NAME)
HDX_API_URL = "https://data.humdata.org/api/3/action/package_show"

MAX_RETRIES = 3
BASE_DELAY_S = 2.0

# Region → default NDVI baseline (0-1). Used for anomaly calc when we
# only receive an absolute NDVI value, not a pre-computed anomaly.
REGION_NDVI_BASELINE = {
    "region_ethiopia":    0.45,
    "region_kenya":       0.40,
    "region_somalia":     0.25,
    "region_sudan":       0.30,
    "region_south_sudan": 0.55,
    "region_uganda":      0.60,
    "region_djibouti":    0.15,
    "region_eritrea":     0.25,
    "region_tanzania":    0.55,
    "region_burundi":     0.60,
    "region_rwanda":      0.62,
}


async def _find_ndvi_resource_url() -> Optional[str]:
    """Find a downloadable NDVI CSV resource URL from HDX.

    Queries the HDX package_show API for the WFP NDVI dataset and picks
    the first CSV resource. Returns the URL or None.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(HDX_API_URL, params={"id": "wfp-ndvi"})
            resp.raise_for_status()
            data = resp.json()
            resources = data.get("result", {}).get("resources", [])
            for res in resources:
                fmt = (res.get("format") or "").lower()
                if "csv" in fmt or res.get("url", "").lower().endswith(".csv"):
                    return res.get("url")
            return None
    except Exception as exc:
        logger.warning("HDX NDVI resource lookup failed: %s", exc)
        return None


async def _download_csv(url: str) -> Optional[str]:
    """Download a CSV file and return its text content."""
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.warning("HDX NDVI CSV download failed: %s", exc)
        return None


def _parse_ndvi_csv(csv_text: str) -> list[dict]:
    """Parse a simple CSV into rows keyed by region.

    Expects at least a region/admin column and an NDVI column. Returns a
    list of dicts with keys: region, ndvi, date (if present).
    """
    import csv
    import io

    rows = list(csv.DictReader(io.StringIO(csv_text)))
    if not rows:
        return []

    # Find candidate columns case-insensitively
    headers = list(rows[0].keys())
    region_col = next((h for h in headers if h.lower() in ("region", "admin1", "admin0", "country", "area")), None)
    ndvi_col = next((h for h in headers if "ndvi" in h.lower()), None)
    date_col = next((h for h in headers if h.lower() in ("date", "period", "time")), None)

    if not region_col or not ndvi_col:
        return []

    parsed = []
    for row in rows:
        region = (row.get(region_col) or "").strip().lower()
        try:
            ndvi = float(row.get(ndvi_col))
        except (TypeError, ValueError):
            continue
        if not region or not (0 <= ndvi <= 1):
            continue
        parsed.append({
            "region": region,
            "ndvi": ndvi,
            "date": (row.get(date_col) or "").strip() if date_col else "",
        })
    return parsed


def _map_to_region(name: str) -> Optional[str]:
    """Map a parsed admin/region name to an IGAD region_id."""
    name = name.lower()
    mapping = {
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
    }
    for key, rid in mapping.items():
        if key in name:
            return rid
    return None


async def fetch_all_regions() -> dict:
    """Fetch WFP NDVI data for all IGAD regions and write NDVISignal nodes.

    Returns summary dict with counts.
    """
    summary = {"total": 0, "success": 0, "failed": 0, "source_id": SOURCE_ID}

    try:
        await upsert_data_source(
            source_id=SOURCE_ID,
            name=SOURCE_NAME,
            url=settings.hdx_ndvi_url,
        )

        csv_url = await _find_ndvi_resource_url()
        if not csv_url:
            logger.warning("No NDVI CSV resource found on HDX for WFP dataset")
            return summary

        csv_text = await _download_csv(csv_url)
        if not csv_text:
            logger.warning("NDVI CSV download failed")
            return summary

        rows = _parse_ndvi_csv(csv_text)
        if not rows:
            logger.warning("No parseable NDVI rows found in CSV")
            return summary

        # Group by region, take the latest value per region
        latest_by_region: dict[str, dict] = {}
        for row in rows:
            region_id = _map_to_region(row["region"])
            if not region_id:
                continue
            if region_id not in latest_by_region:
                latest_by_region[region_id] = row
            elif row["date"] > latest_by_region[region_id]["date"]:
                latest_by_region[region_id] = row

        for region_id, row in latest_by_region.items():
            summary["total"] += 1
            try:
                baseline = REGION_NDVI_BASELINE.get(region_id, 0.4)
                anomaly = row["ndvi"] - baseline
                date_str = row["date"] or datetime.now(timezone.utc).strftime("%Y-%m-%d")

                signal_id = f"ndvi_{region_id}_{date_str}"
                await upsert_ndvi_signal(
                    signal_id=signal_id,
                    ndvi_value=row["ndvi"],
                    anomaly=round(anomaly, 4),
                    date=date_str,
                    region_id=region_id,
                )

                # Create MEASURED_IN relationship
                await neo4j_client.execute_write(
                    """
                    MATCH (ns:NDVISignal {id: $signal_id})
                    MATCH (r:Region {id: $region_id})
                    MERGE (ns)-[:MEASURED_IN]->(r)
                    """,
                    {"signal_id": signal_id, "region_id": region_id},
                )

                # Record lineage
                await record_lineage(signal_id, SOURCE_ID)
                summary["success"] += 1
                logger.info("NDVI %s: value=%.3f anomaly=%+.3f", region_id, row["ndvi"], anomaly)

            except Exception as exc:
                summary["failed"] += 1
                logger.error("NDVI failed for %s: %s", region_id, exc)

        await update_data_source_stats(
            source_id=SOURCE_ID,
            record_count=summary["success"],
            hash_value=hashlib.sha256(str(summary).encode()).hexdigest()[:32],
        )

    except Exception as exc:
        logger.error("NDVI fetch_all_regions failed: %s", exc)

    logger.info("NDVI ingestion complete: %d success, %d failed", summary["success"], summary["failed"])
    return summary