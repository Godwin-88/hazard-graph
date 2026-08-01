"""HazardGraph — Compound risk scoring service.

Computes weighted composite risk scores for all IGAD regions
using rainfall, food prices, IPC, SDE, and network signals.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

from db.neo4j_client import neo4j_client
from db.postgres_client import async_session_factory
from db.redis_client import redis_client
from risk.vulnerability_data import get_vulnerability_multiplier

logger = logging.getLogger(__name__)


@dataclass
class RegionRiskScore:
    region_id: str
    name: str
    country: str
    score: float
    delta: float
    components: dict
    vulnerability_multiplier: float
    current_regime: str
    alert_triggered: bool


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _compute_rainfall_score(spi_30d_smoothed: float) -> float:
    return _clip((-spi_30d_smoothed + 1.5) / 3.0, 0.0, 1.0)


def _compute_food_score(pct_change_30d: float) -> float:
    return _clip(pct_change_30d / 0.50, 0.0, 1.0)


def _compute_ipc_score(ipc_phase: float) -> float:
    return _clip((ipc_phase - 1.0) / 4.0, 0.0, 1.0)


def _compute_sde_score(p_drought: float, p_flood: float) -> float:
    return max(p_drought, p_flood)


async def compute_risk_scores(neo4j_session) -> list[RegionRiskScore]:
    """Compute compound risk score for all 11 IGAD regions.

    Pipeline:
      1. Fetch latest signals from Neo4j (Rainfall, FoodPrice, IPC, SDE, Region)
      2. Compute component scores (all 0-1)
      3. Apply vulnerability multiplier
      4. Normalise across regions (0-100)
      5. Fetch previous score from PostgreSQL for delta
      6. Write to Neo4j + PostgreSQL
      7. Return list[RegionRiskScore]
    """
    regions_query = """
    MATCH (r:Region)
    OPTIONAL MATCH (rs:RainfallSignal)-[:MEASURED_IN]->(r)
    WITH r, collect(DISTINCT rs)[0] AS rs
    OPTIONAL MATCH (fs:FoodPriceSignal)-[:MEASURED_IN]->(r)
    WITH r, rs, collect(DISTINCT fs)[0] AS fs
    OPTIONAL MATCH (is_:IPCPhaseSignal)-[:MEASURED_IN]->(r)
    WITH r, rs, fs, collect(DISTINCT is_)[0] AS is_
    OPTIONAL MATCH (ss:StochasticSignal)-[:MEASURED_IN]->(r)
    WITH r, rs, fs, is_, collect(DISTINCT ss)[0] AS ss
    RETURN r.id AS region_id,
           r.name AS name,
           r.country AS country,
           r.current_regime AS regime,
           coalesce(r.pagerank_score, 0.5) AS pagerank_score,
           rs.spi_30d_smoothed AS spi,
           rs.anomaly_pct AS anomaly_pct,
           fs.pct_change_30d AS pct_change_30d,
           is_.phase AS ipc_phase,
           ss.p_drought_4w AS p_drought_4w,
           ss.p_flood_4w AS p_flood_4w,
           rs.created_at AS rainfall_created_at,
           fs.created_at AS food_created_at,
           is_.created_at AS ipc_created_at,
           ss.created_at AS stochastic_created_at
    ORDER BY r.name
    """
    regions = await neo4j_client.execute_read(regions_query)

    raw_scores: list[tuple[str, str, str, float, dict]] = []
    now = datetime.now(timezone.utc)

    for region in regions:
        region_id = region["region_id"]
        name = region["name"]
        country = region.get("country", "").lower()
        regime = region.get("regime", "Baseline") or "Baseline"

        spi = region.get("spi") or 0.0
        anomaly = region.get("anomaly_pct") or 0.0
        pct_change = region.get("pct_change_30d") or 0.0
        ipc_phase = region.get("ipc_phase") or 1.0
        p_drought = region.get("p_drought_4w") or 0.0
        p_flood = region.get("p_flood_4w") or 0.0
        pagerank = region.get("pagerank_score") or 0.5

        rainfall_score = _compute_rainfall_score(spi)
        food_score = _compute_food_score(pct_change)
        ipc_score = _compute_ipc_score(ipc_phase)
        sde_score = _compute_sde_score(p_drought, p_flood)
        network_score = _clip(pagerank, 0.0, 1.0)

        vm = get_vulnerability_multiplier(country)

        raw_score = (
            rainfall_score * 0.30
            + food_score * 0.20
            + ipc_score * 0.25
            + sde_score * 0.15
            + network_score * 0.10
        ) * vm

        components = {
            "rainfall": round(rainfall_score, 4),
            "food": round(food_score, 4),
            "ipc": round(ipc_score, 4),
            "sde": round(sde_score, 4),
            "network": round(network_score, 4),
        }

        raw_scores.append((region_id, name, country, raw_score, components, vm, regime))

    if not raw_scores:
        return []

    raw_values = [r[3] for r in raw_scores]
    min_raw = min(raw_values)
    max_raw = max(raw_values)
    raw_range = max_raw - min_raw if max_raw != min_raw else 1.0

    results: list[RegionRiskScore] = []

    for region_id, name, country, raw_score, components, vm, regime in raw_scores:
        normalised = (raw_score - min_raw) / raw_range * 100.0

        delta = 0.0
        try:
            async with async_session_factory() as db_session:
                from sqlalchemy import text
                result = await db_session.execute(
                    text("SELECT score FROM risk_history WHERE region_id = :rid ORDER BY computed_at DESC LIMIT 1"),
                    {"rid": region_id},
                )
                row = result.fetchone()
                if row:
                    delta = round(normalised - row[0], 2)
        except Exception as exc:
            logger.warning("Failed to fetch previous score for %s: %s", region_id, exc)

        alert_triggered = normalised > 60.0 or abs(delta) > 15.0

        score_entry = RegionRiskScore(
            region_id=region_id,
            name=name,
            country=country,
            score=round(normalised, 2),
            delta=delta,
            components=components,
            vulnerability_multiplier=round(vm, 4),
            current_regime=regime,
            alert_triggered=alert_triggered,
        )
        results.append(score_entry)

        try:
            await neo4j_client.execute_write(
                "MATCH (r:Region {id: $region_id}) SET r.current_risk_score = $score",
                {"region_id": region_id, "score": score_entry.score},
            )
        except Exception as exc:
            logger.warning("Failed to update Neo4j score for %s: %s", region_id, exc)

        try:
            async with async_session_factory() as db_session:
                await db_session.execute(
                    text(
                        "INSERT INTO risk_history (region_id, score, delta, component_scores_json, vulnerability_multiplier, current_regime, computed_at) "
                        "VALUES (:rid, :score, :delta, :components, :vm, :regime, :now)"
                    ),
                    {
                        "rid": region_id,
                        "score": score_entry.score,
                        "delta": score_entry.delta,
                        "components": json.dumps(components),
                        "vm": vm,
                        "regime": regime,
                        "now": now,
                    },
                )
                await db_session.commit()
        except Exception as exc:
            logger.warning("Failed to write risk_history for %s: %s", region_id, exc)

    return results