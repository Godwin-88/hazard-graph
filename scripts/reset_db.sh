#!/bin/bash
echo "► Resetting development databases..."
docker compose down -v          # remove volumes
docker compose up -d            # fresh start
echo "► Waiting for services..."
sleep 30
echo "► Running schema migration..."
python -c "
import asyncio
from db.neo4j_client import get_driver
async def migrate():
  driver = get_driver()
  async with driver.session() as s:
    with open('migrations/001_schema.cypher') as f:
      sql = f.read()
    for stmt in sql.split(';'):
      stmt = stmt.strip()
      if stmt: await s.run(stmt)
  await driver.close()
asyncio.run(migrate())
"
echo "► Seeding demo data..."
python scripts/seed_demo_data.py
echo "✅ Databases reset and seeded."