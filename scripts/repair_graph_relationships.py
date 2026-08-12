"""One-time graph relationship repair.

Heals existing orphaned nodes in the remote Neo4j so the Graph Explorer
renders a fully connected knowledge graph. Uses the same idempotent
reconcile_graph_relationships() as the pipeline, so it's safe to re-run.

Usage:
  cd /home/ed/projects/hazardgraph && python scripts/repair_graph_relationships.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from db.neo4j_client import neo4j_client
from graph.node_writers import reconcile_graph_relationships


async def main():
    print("Connecting to Neo4j...")
    await neo4j_client.connect()
    print("Running graph relationship reconciliation...")
    summary = await reconcile_graph_relationships()
    print("\n=== RECONCILE SUMMARY ===")
    for key, value in summary.items():
        print(f"  {key:30s} {value}")
    print("\nDone. The Graph Explorer should now show a connected graph.")
    await neo4j_client.close()


if __name__ == "__main__":
    asyncio.run(main())