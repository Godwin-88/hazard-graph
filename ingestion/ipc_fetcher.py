"""HazardGraph — IPC food insecurity phase data fetcher.

Fetches IPC acute food insecurity phase data for IGAD countries.
Primary source: IPC API (https://api.ipcinfo.org).
Fallback: FEWS NET API (https://fdw.fews.net/api) with JWT auth.
Writes IPCPhaseSignal nodes to Neo4j and creates alerts for phase ≥ 3.
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from config.settings import settings
from db.neo4j_client import neo4j_client
from db.postgres_client import async_session_factory
from db.redis_client import redis_client
from graph.node_writers import upsert_ipc_phase_signal, upsert_data_source, make_data_source_id
from graph.lineage import record_lineage, update_data_source_stats
from models.postgres.alerts import Alert, AlertStatus

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────
IPC_SOURCE_NAME = "IPC Acute Food Insecurity"
IPC_SOURCE_ID = make_data_source_id(IPC_SOURCE_NAME)
FEWS_SOURCE_NAME = "FEWS NET IPC Data"
FEWS_SOURCE_ID = make_data_source_id(FEWS_SOURCE_NAME)

MAX_RETRIES = 3
BASE_DELAY_S = 2.0

# ISO3 → region_id mapping
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

# ── FEWS NET JWT Token Cache ──────────────────────────────
_fews_token: str | None = None
_fews_token_expiry: float = 0.0


async def _get_fews_net_token() -> str | None:
    """Authenticate with FEWS NET API and return a JWT token.

    POSTs credentials to https://fdw.fews.net/api-token-auth/.
    Caches the token in memory for 23 hours (tokens typically last 24h).
    """
    global _fews_token, _fews_token_expiry

    # Return cached token if still valid (23h window)
    if _fews_token and time.time() < _fews_token_expiry:
        return _fews_token

    username = settings.fews_net_username
    password = settings.fews_net_password
    if not username or not password:
        logger.warning("FEWS NET credentials not configured in .env")
        return None

    auth_url = f"{settings.fews_net_base_url}/api-token-auth/"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                auth_url,
                data={"username": username, "password": password},
            )
            response.raise_for_status()
            data = response.json()
            _fews_token = data["token"]
            # Cache for 23 hours (tokens typically last 24h)
            _fews_token_expiry = time.time() + 23 * 3600
            logger.info("FEWS NET JWT token obtained successfully")
            return _fews_token
    except Exception as exc:
        logger.error("FEWS NET authentication failed: %s", exc)
        return None


async def _fetch_json_with_auth(url: str, token: str, timeout: int = 30) -> Optional[dict | list]:
    """Fetch JSON from a URL using JWT Bearer auth with retry logic."""
    async def _fetch():
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"JWT {token}"},
            )
            response.raise_for_status()
            return response.json()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await _fetch()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                # Token may have expired — clear cache and retry once
                global _fews_token, _fews_token_expiry
                _fews_token = None
                _fews_token_expiry = 0.0
                new_token = await _get_fews_net_token()
                if new_token:
                    # Retry with new token
                    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                        response = await client.get(
                            url,
                            headers={"Authorization": f"JWT {new_token}"},
                        )
                        response.raise_for_status()
                        return response.json()
                return None
            if attempt < MAX_RETRIES:
                delay = BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning("FEWS NET API error, attempt %d/%d: %s. Retry in %.1fs", attempt, MAX_RETRIES, exc, delay)
                await asyncio.sleep(delay)
            else:
                logger.error("FEWS NET API failed after %d attempts: %s", MAX_RETRIES, exc)
                return None
        except Exception as exc:
            logger.error("FEWS NET API request error: %s", exc)
            return None
    return None


async def _fetch_json(url: str, timeout: int = 30) -> Optional[dict]:
    """Fetch JSON from a URL with retry logic (no auth)."""
    async def _fetch():
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await _fetch()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (404, 503):
                logger.warning("IPC API unavailable (%d): %s", exc.response.status_code, url)
                return None
            if attempt < MAX_RETRIES:
                delay = BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning("IPC API error, attempt %d/%d: %s. Retry in %.1fs", attempt, MAX_RETRIES, exc, delay)
                await asyncio.sleep(delay)
            else:
                logger.error("IPC API failed after %d attempts: %s", MAX_RETRIES, exc)
                return None
        except Exception as exc:
            logger.error("IPC API request error: %s", exc)
            return None
    return None


async def fetch_from_ipc_api() -> list[dict]:
    """Try to fetch IPC data from the official IPC API.

    Returns list of phase data dicts with keys:
        iso3, phase, population_affected, reference_period
    """
    url = "https://api.ipcinfo.org/country?format=json"
    data = await _fetch_json(url)

    if not data:
        return []

    results = []
    countries = data if isinstance(data, list) else data.get("results", data.get("data", []))

    for country in countries:
        iso3 = (country.get("iso3", country.get("country_code", ""))).upper()
        if iso3 not in ISO3_TO_REGION:
            continue

        phase = country.get("phase", country.get("current_phase", 0))
        if isinstance(phase, str):
            try:
                phase = int(phase)
            except ValueError:
                phase = 0

        population = country.get("population_affected", country.get("population", 0))
        reference = country.get("reference_period", country.get("analysis_date", str(datetime.now(timezone.utc).year)))

        results.append({
            "iso3": iso3,
            "region_id": ISO3_TO_REGION[iso3],
            "phase": phase,
            "population_affected": int(population),
            "reference_date": str(reference),
            "source": "ipc_api",
        })

    logger.info("IPC API returned data for %d IGAD countries", len(results))
    return results


async def fetch_from_fews_net(iso3: str) -> Optional[dict]:
    """Fetch IPC data from FEWS NET API for a single country using JWT auth.

    Uses the correct base URL: https://fdw.fews.net/api
    Authenticates via POST to /api-token-auth/ then uses JWT Bearer token.
    """
    token = await _get_fews_net_token()
    if not token:
        logger.warning("No FEWS NET token available for %s", iso3)
        return None

    # Try multiple possible endpoints for IPC phase data
    endpoints = [
        f"{settings.fews_net_base_url}/ipc/?format=json&country={iso3}",
        f"{settings.fews_net_base_url}/ipcphase/?format=json&country={iso3}",
        f"{settings.fews_net_base_url}/ipcclassification/?format=json&country={iso3}",
    ]

    for url in endpoints:
        data = await _fetch_json_with_auth(url, token)
        if data:
            # Parse the response — could be list or dict
            entries = data if isinstance(data, list) else data.get("results", data.get("data", [data]))
            if entries and len(entries) > 0:
                entry = entries[0] if isinstance(entries, list) else entries

                phase = entry.get("phase", entry.get("ipc_phase", entry.get("classification", entry.get("ipc", 0))))
                if isinstance(phase, str):
                    try:
                        phase = int(phase)
                    except ValueError:
                        phase = 0

                population = entry.get("population_affected", entry.get("population", entry.get("affected_population", 0)))
                reference = entry.get(
                    "reference_date",
                    entry.get("analysis_date", entry.get("date", str(datetime.now(timezone.utc).year))),
                )

                logger.info("FEWS NET returned data for %s: Phase %d", iso3, phase)
                return {
                    "iso3": iso3,
                    "region_id": ISO3_TO_REGION.get(iso3, ""),
                    "phase": phase,
                    "population_affected": int(population),
                    "reference_date": str(reference),
                    "source": "fews_net",
                }

    logger.warning("No FEWS NET data found for %s across any endpoint", iso3)
    return None


async def fetch_all_countries() -> dict:
    """Fetch IPC data for all IGAD countries.

    Returns summary dict with counts.
    """
    summary = {
        "total_countries": 0,
        "signals_written": 0,
        "alerts_created": 0,
        "phase_3plus": 0,
        "errors": 0,
        "source": "ipc_api",
        "source_id": IPC_SOURCE_ID,
    }

    try:
        # Try primary source first
        all_phases = await fetch_from_ipc_api()

        if not all_phases:
            # Fall back to FEWS NET per country
            logger.info("IPC API returned no data. Falling back to FEWS NET...")
            summary["source"] = "fews_net"
            all_phases = []

            for iso3 in ISO3_TO_REGION:
                summary["total_countries"] += 1
                phase_data = await fetch_from_fews_net(iso3)
                if phase_data:
                    all_phases.append(phase_data)

            source_id = FEWS_SOURCE_ID
            source_name = FEWS_SOURCE_NAME
        else:
            summary["total_countries"] = len(all_phases)
            source_id = IPC_SOURCE_ID
            source_name = IPC_SOURCE_NAME

        if not all_phases:
            logger.warning("No IPC data available from any source")
            return summary

        # Ensure DataSource node exists
        await upsert_data_source(
            source_id=source_id,
            name=source_name,
            url="https://api.ipcinfo.org/country",
        )

        for phase_data in all_phases:
            try:
                region_id = phase_data["region_id"]
                if not region_id:
                    continue

                signal_id = f"ipc_{region_id}_{phase_data['reference_date']}"

                await upsert_ipc_phase_signal(
                    signal_id=signal_id,
                    phase=phase_data["phase"],
                    population_affected=phase_data["population_affected"],
                    reference_date=phase_data["reference_date"],
                    region_id=region_id,
                )

                # Create MEASURED_IN relationship
                await neo4j_client.execute_write(
                    """
                    MATCH (ipc:IPCPhaseSignal {id: $signal_id})
                    MATCH (r:Region {id: $region_id})
                    MERGE (ipc)-[:MEASURED_IN]->(r)
                    """,
                    {"signal_id": signal_id, "region_id": region_id},
                )

                # Record lineage
                await record_lineage(signal_id, source_id)

                summary["signals_written"] += 1

                # Check for phase >= 3 (crisis or worse)
                if phase_data["phase"] >= 3:
                    summary["phase_3plus"] += 1
                    # Create alert
                    try:
                        async with async_session_factory() as session:
                            phase_names = {1: "Minimal", 2: "Stressed", 3: "Crisis", 4: "Emergency", 5: "Famine"}
                            phase_name = phase_names.get(phase_data["phase"], f"Phase {phase_data['phase']}")

                            alert = Alert(
                                region_id=region_id,
                                language="en",
                                message_text=(
                                    f"IPC {phase_name} (Phase {phase_data['phase']}) detected in {region_id}. "
                                    f"Population affected: {phase_data['population_affected']:,}. "
                                    f"Reference: {phase_data['reference_date']}"
                                ),
                                risk_score_at_trigger=min(phase_data["phase"] / 5.0, 1.0),
                                generated_at=datetime.now(timezone.utc),
                                status=AlertStatus.PENDING,
                                kelly_priority=min(phase_data["phase"] / 5.0, 1.0),
                            )
                            session.add(alert)
                            await session.commit()
                            summary["alerts_created"] += 1
                            logger.info("IPC alert created for %s: Phase %d", region_id, phase_data["phase"])
                    except Exception as exc:
                        logger.error("Failed to create IPC alert: %s", exc)

            except Exception as exc:
                summary["errors"] += 1
                logger.error("Failed to process IPC data for %s: %s", phase_data.get("iso3", "?"), exc)

        # Update DataSource stats
        await update_data_source_stats(
            source_id=source_id,
            record_count=summary["signals_written"],
            hash_value=hashlib.sha256(str(all_phases).encode()).hexdigest()[:32],
        )

    except Exception as exc:
        logger.error("IPC fetch_all_countries failed: %s", exc)
        summary["errors"] += 1

    logger.info(
        "IPC ingestion complete: %d signals, %d phase3+, %d alerts from %s",
        summary["signals_written"], summary["phase_3plus"], summary["alerts_created"], summary["source"],
    )
    return summary