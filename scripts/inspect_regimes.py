"""Read-only diagnostic: check Region.current_regime values + HazardRegime nodes."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from neo4j import AsyncGraphDatabase


async def main():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        async with driver.session() as session:
            print("=== Region nodes: id / current_regime ===")
            res = await session.run(
                "MATCH (r:Region) RETURN r.id AS id, r.current_regime AS regime "
                "ORDER BY r.id"
            )
            async for rec in res:
                print(f"  {rec['id']:25s} regime={rec['regime']!r}")

            print("\n=== HazardRegime nodes (id / name) ===")
            res = await session.run(
                "MATCH (hr:HazardRegime) RETURN hr.id AS id, hr.name AS name ORDER BY hr.id"
            )
            async for rec in res:
                print(f"  {rec['id']:25s} name={rec['name']!r}")

            print("\n=== Existing IN_REGIME relationships ===")
            res = await session.run("MATCH (:Region)-[r:IN_REGIME]->(:HazardRegime) RETURN count(r) AS cnt")
            print(f"  count: {(await res.single())['cnt']}")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())