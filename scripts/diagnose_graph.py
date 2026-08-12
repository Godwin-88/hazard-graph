"""Read-only diagnostic: inspect Neo4j node/relationship state.

Connects to the remote Neo4j from .env and reports:
- node counts by label
- relationship counts by type
- which nodes have NO relationships at all
- sample of relationship endpoints (to check id matching)
"""
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
    print(f"Connecting to {uri} ...")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        async with driver.session() as session:
            # 1. Node counts by label
            res = await session.run(
                "MATCH (n) UNWIND labels(n) AS lbl RETURN lbl AS label, count(*) AS cnt ORDER BY cnt DESC"
            )
            print("\n=== NODE COUNTS BY LABEL ===")
            async for rec in res:
                print(f"  {rec['label']:25s} {rec['cnt']}")

            # 2. Relationship counts by type
            res = await session.run(
                "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS cnt ORDER BY cnt DESC"
            )
            print("\n=== RELATIONSHIP COUNTS BY TYPE ===")
            async for rec in res:
                print(f"  {rec['rel']:25s} {rec['cnt']}")

            # 3. Nodes with NO relationships
            res = await session.run(
                "MATCH (n) WHERE NOT (n)--() RETURN labels(n) AS labels, n.id AS id LIMIT 30"
            )
            print("\n=== NODES WITH NO RELATIONSHIPS (sample 30) ===")
            async for rec in res:
                print(f"  {rec['labels']}  id={rec['id']}")

            # 4. Sample relationship endpoints (check id matching)
            res = await session.run(
                "MATCH (a)-[r]->(b) RETURN labels(a) AS src_lbl, a.id AS src_id, "
                "type(r) AS rel, labels(b) AS tgt_lbl, b.id AS tgt_id LIMIT 20"
            )
            print("\n=== SAMPLE RELATIONSHIP ENDPOINTS (20) ===")
            async for rec in res:
                print(f"  {rec['src_lbl']}({rec['src_id']}) -[{rec['rel']}]-> {rec['tgt_lbl']}({rec['tgt_id']})")

            # 5. Total counts
            res = await session.run("MATCH (n) RETURN count(n) AS nodes")
            nodes = (await res.single())["nodes"]
            res = await session.run("MATCH ()-[r]->() RETURN count(r) AS rels")
            rels = (await res.single())["rels"]
            print(f"\n=== TOTALS: {nodes} nodes, {rels} relationships ===")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())