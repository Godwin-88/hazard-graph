"""
HazardGraph — Data Inspection Script

Queries Neo4j, PostgreSQL, and Redis to show what data
has been ingested from each source.

Usage:
  docker compose exec app python scripts/inspect_data.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()


async def inspect_neo4j(neo4j_session):
    """Query Neo4j for node/edge counts per label/type."""
    print("\n  ── Neo4j Node Counts ──")
    queries = [
        ("Total nodes", "MATCH (n) RETURN count(n) AS c"),
        ("Region", "MATCH (n:Region) RETURN count(n) AS c"),
        ("RainfallSignal", "MATCH (n:RainfallSignal) RETURN count(n) AS c"),
        ("FoodPriceSignal", "MATCH (n:FoodPriceSignal) RETURN count(n) AS c"),
        ("IPCPhaseSignal", "MATCH (n:IPCPhaseSignal) RETURN count(n) AS c"),
        ("NDVISignal", "MATCH (n:NDVISignal) RETURN count(n) AS c"),
        ("ConflictSignal", "MATCH (n:ConflictSignal) RETURN count(n) AS c"),
        ("ForecastSignal", "MATCH (n:ForecastSignal) RETURN count(n) AS c"),
        ("CausalEdge", "MATCH (n:CausalEdge) RETURN count(n) AS c"),
        ("StochasticSignal", "MATCH (n:StochasticSignal) RETURN count(n) AS c"),
        ("MLForecast", "MATCH (n:MLForecast) RETURN count(n) AS c"),
        ("BMAScore", "MATCH (n:BMAScore) RETURN count(n) AS c"),
        ("HazardRegime", "MATCH (n:HazardRegime) RETURN count(n) AS c"),
        ("HazardType", "MATCH (n:HazardType) RETURN count(n) AS c"),
        ("HazardCluster", "MATCH (n:HazardCluster) RETURN count(n) AS c"),
        ("DataSource", "MATCH (n:DataSource) RETURN count(n) AS c"),
        ("Alert (Neo4j)", "MATCH (n:Alert) RETURN count(n) AS c"),
        ("GraphSnapshot", "MATCH (n:GraphSnapshot) RETURN count(n) AS c"),
    ]

    for label, query in queries:
        try:
            result = await neo4j_session.run(query)
            record = await result.single()
            count = record["c"] if record else 0
            print(f"     {label:20s} → {count}")
        except Exception as e:
            print(f"     {label:20s} → ERROR: {e}")

    print("\n  ── Neo4j Regions with Risk Scores ──")
    try:
        result = await neo4j_session.run(
            "MATCH (r:Region) RETURN r.id AS id, r.name AS name, "
            "r.current_risk_score AS risk, r.current_regime AS regime "
            "ORDER BY r.current_risk_score DESC"
        )
        async for record in result:
            rid = record["id"] or "?"
            name = record["name"] or rid
            risk = record["risk"] or 0.0
            regime = record["regime"] or "none"
            bar = "█" * int(float(risk) / 5) if risk else ""
            print(f"     {name:15s}  risk={float(risk):5.1f}  {bar}  {regime}")
    except Exception as e:
        print(f"     ERROR: {e}")

    print("\n  ── Neo4j CausalEdge Count per Region ──")
    try:
        result = await neo4j_session.run(
            "MATCH (e:CausalEdge) RETURN e.region_id AS region, "
            "count(e) AS edges, avg(e.weight) AS avg_w "
            "ORDER BY edges DESC"
        )
        async for record in result:
            print(f"     {record['region']:20s} → {record['edges']} edges, "
                  f"avg weight={record['avg_w']:.3f}")
    except Exception as e:
        print(f"     ERROR: {e}")

    print("\n  ── Neo4j Relationship Types ──")
    try:
        result = await neo4j_session.run(
            "CALL db.relationshipTypes() YIELD relationshipType "
            "RETURN relationshipType ORDER BY relationshipType"
        )
        async for record in result:
            print(f"     {record['relationshipType']}")
    except Exception as e:
        print(f"     ERROR: {e}")


async def inspect_postgres(postgres_session):
    """Query PostgreSQL for alert and job run counts."""
    from sqlalchemy import text

    print("\n  ── PostgreSQL Alert Counts ──")
    try:
        result = await postgres_session.execute(
            text("SELECT status, count(*) FROM alerts GROUP BY status ORDER BY status")
        )
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"     {row[0]:15s} → {row[1]}")
        else:
            print("     No alerts found")
    except Exception as e:
        print(f"     ERROR: {e}")

    print("\n  ── PostgreSQL Alerts Detail ──")
    try:
        result = await postgres_session.execute(
            text("SELECT id, region_id, status, risk_score_at_trigger, "
                 "generated_at FROM alerts ORDER BY generated_at DESC LIMIT 10")
        )
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"     #{row[0]}  {row[1]:20s}  {row[2]:10s}  "
                      f"risk={row[3]:.1f}  {row[4]}")
        else:
            print("     No alerts found")
    except Exception as e:
        print(f"     ERROR: {e}")

    print("\n  ── PostgreSQL Job Run History ──")
    try:
        result = await postgres_session.execute(
            text("SELECT job_name, status, records_processed, started_at "
                 "FROM job_runs ORDER BY started_at DESC LIMIT 15")
        )
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"     {row[0]:30s}  {row[1]:10s}  "
                      f"records={row[2]}  {row[3]}")
        else:
            print("     No job runs recorded yet")
    except Exception as e:
        print(f"     ERROR: {e}")


async def inspect_redis():
    """Check Redis for cached analytics and scoring keys."""
    from db.redis_client import redis_client

    print("\n  ── Redis Cache Keys ──")
    try:
        await redis_client.connect()
        keys = await redis_client._redis.keys("analytics:*")
        keys += await redis_client._redis.keys("graph:*")
        keys += await redis_client._redis.keys("risk:*")
        keys += await redis_client._redis.keys("chirps:*")
        keys += await redis_client._redis.keys("regime_posteriors:*")
        keys += await redis_client._redis.keys("wfp:*")
        keys += await redis_client._redis.keys("nasa_power:*")
        keys += await redis_client._redis.keys("faostat:*")
        keys += await redis_client._redis.keys("ndvi:*")
        keys += await redis_client._redis.keys("acled:*")

        if keys:
            for key in sorted(set(keys)):
                ttl = await redis_client._redis.ttl(key)
                print(f"     {key}  (TTL={ttl}s)")
        else:
            print("     No cached keys found")
    except Exception as e:
        print(f"     ERROR: {e}")
    finally:
        await redis_client.close()


async def inspect():
    """Run all inspections."""
    from db.neo4j_client import neo4j_client
    from db.postgres_client import async_session_factory

    print("=" * 60)
    print("  HazardGraph — Data Inspection")
    print("=" * 60)

    # Neo4j
    print("\n📊 Neo4j:")
    await neo4j_client.connect()
    async with neo4j_client.get_session() as session:
        await inspect_neo4j(session)
    await neo4j_client.close()

    # PostgreSQL
    print("\n📊 PostgreSQL:")
    async with async_session_factory() as pg:
        await inspect_postgres(pg)

    # Redis
    print("\n📊 Redis:")
    await inspect_redis()

    print("\n" + "=" * 60)
    print("  Inspection complete")
    print("=" * 60)
    print()
    print("  Quick Cypher queries (docker compose exec neo4j cypher-shell):")
    print("    MATCH (n) RETURN labels(n) AS type, count(n) AS count")
    print("    MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS count")
    print()
    print("  Quick SQL query (docker compose exec postgres psql -U hazardgraph -d hazardgraph):")
    print("    SELECT status, count(*) FROM alerts GROUP BY status;")
    print("    SELECT job_name, status FROM job_runs ORDER BY started_at DESC LIMIT 10;")
    print()


if __name__ == '__main__':
    asyncio.run(inspect())