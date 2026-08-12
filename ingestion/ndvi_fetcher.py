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

# WFP NDVI is published per-country on HDX (not as a single global package).
# Package IDs follow the pattern "{iso3}-ndvi-subnational".
NDVI_PACKAGE_IDS = {
    "ETH": "eth-ndvi-subnational",
    "KEN": "ken-ndvi-subnational",
    "SOM": "som-ndvi-subnational",
    "SDN": "sdn-ndvi-subnational",
    "SSD": "ssd-ndvi-subnational",
    "UGA": "uga-ndvi-subnational",
    "DJI": "dji-ndvi-subnational",
    "ERI": "eri-ndvi-subnational",
    "TZA": "tza-ndvi-subnational",
    "BDI": "bdi-ndvi-subnational",
    "RWA": "rwa-ndvi-subnational",
}

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


async def _find_ndvi_resource_url(package_id: str) -> Optional[str]:
    """Find a downloadable NDVI CSV resource URL from HDX.

    Queries the HDX package_show API for a single country's NDVI dataset
    and picks the first CSV resource. Returns the URL or None.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(HDX_API_URL, params={"id": package_id})
            resp.raise_for_status()
            data = resp.json()
            resources = data.get("result", {}).get("resources", [])
            for res in resources:
                fmt = (res.get("format") or "").lower()
                if "csv" in fmt or res.get("url", "").lower().endswith(".csv"):
                    return res.get("url")
            return None
    except Exception as exc:
        logger.warning("HDX NDVI resource lookup failed for %s: %s", package_id, exc)
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
    """Parse a WFP/HDX NDVI CSV into rows.

    The WFP NDVI subnational datasets use columns like:
      date, adm_level, adm_id, PCODE, n_pixels, vim, vim_avg, viq

    `vim` is the smoothed NDVI value (0-1). Each file is country-level,
    so rows are aggregated and the `region` field is set to the caller's
    ISO3 fallback for country-level mapping.

    Returns a list of dicts with keys: region (iso3), ndvi, date.
    """
    import csv
    import io

    rows = list(csv.DictReader(io.StringIO(csv_text)))
    if not rows:
        return []

    headers = list(rows[0].keys())
    header_lower = {h.lower(): h for h in headers}

    # NDVI value column — WFP uses `vim` (smoothed NDVI); fall back to any
    # header containing "ndvi" or "vim".
    ndvi_col = None
    if "vim" in header_lower:
        ndvi_col = header_lower["vim"]
    else:
        ndvi_col = next(
            (h for h in headers if "ndvi" in h.lower() or h.lower() == "vim"),
            None,
        )

    # Date column
    date_col = next(
        (h for h in headers if h.lower() in ("date", "period", "time")),
        None,
    )

    if not ndvi_col:
        return []

    parsed = []
    for row in rows:
        try:
            ndvi = float(row.get(ndvi_col))
        except (TypeError, ValueError):
            continue
        # WFP NDVI values are scaled 0-1
        if not (0 <= ndvi <= 1):
            # Some datasets scale 0-100
            if 0 <= ndvi <= 100:
                ndvi = ndvi / 100.0
            else:
                continue
        parsed.append({
            "region": "",  # filled by caller using ISO3 fallback
            "ndvi": ndvi,
            "date": (row.get(date_col) or "").strip() if date_col else "",
        })
    return parsed


def _map_to_region(name: str) -> Optional[str]:
    """Map a parsed admin/region name or ISO3 code to an IGAD region_id."""
    name = name.strip().lower()

    # Direct ISO3 mapping
    iso3_map = {
        "eth": "region_ethiopia",
        "ken": "region_kenya",
        "som": "region_somalia",
        "sdn": "region_sudan",
        "ssd": "region_south_sudan",
        "uga": "region_uganda",
        "dji": "region_djibouti",
        "eri": "region_eritrea",
        "tza": "region_tanzania",
        "bdi": "region_burundi",
        "rwa": "region_rwanda",
    }
    if name in iso3_map:
        return iso3_map[name]

    # Map by country name (substring match)
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

        # Countries to fetch come from settings (comma-separated ISO3), defaulting
        # to the core IGAD set. Each country package is queried independently.
        countries_raw = settings.ndvi_countries or "ETH,KEN,SOM,SDN"
        countries = [c.strip().upper() for c in countries_raw.split(",") if c.strip()]

        latest_by_region: dict[str, dict] = {}
        for iso3 in countries:
            package_id = NDVI_PACKAGE_IDS.get(iso3)
            if not package_id:
                logger.warning("No NDVI package ID mapped for %s — skipping", iso3)
                continue

            csv_url = await _find_ndvi_resource_url(package_id)
            if not csv_url:
                logger.warning("No NDVI CSV resource found for %s (%s)", iso3, package_id)
                continue

            csv_text = await _download_csv(csv_url)
            if not csv_text:
                logger.warning("NDVI CSV download failed for %s", iso3)
                continue

            rows = _parse_ndvi_csv(csv_text)
            if not rows:
                logger.warning("No parseable NDVI rows found for %s", iso3)
                continue

            # Aggregate by date: take the average NDVI across admin areas for
            # the latest date, mapped to the country-level region.
            region_id = _map_to_region(iso3)
            if not region_id:
                logger.warning("No region mapping for ISO3 %s — skipping", iso3)
                continue

            # Group rows by date and compute the average per date
            from collections import defaultdict
            by_date = defaultdict(list)
            for row in rows:
                by_date[row["date"]].append(row["ndvi"])

            if not by_date:
                logger.warning("No dated NDVI rows found for %s", iso3)
                continue

            # Take the latest date (max string works for YYYY-MM-DD)
            latest_date = max(by_date.keys())
            latest_ndvi = sum(by_date[latest_date]) / len(by_date[latest_date])

            if region_id not in latest_by_region:
                latest_by_region[region_id] = {
                    "region": region_id,
                    "ndvi": latest_ndvi,
                    "date": latest_date,
                }
            elif latest_date > latest_by_region[region_id]["date"]:
                latest_by_region[region_id] = {
                    "region": region_id,
                    "ndvi": latest_ndvi,
                    "date": latest_date,
                }

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