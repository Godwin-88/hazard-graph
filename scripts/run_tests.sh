#!/bin/bash
set -e
echo "═══════════════════════════════════════"
echo "  HazardGraph Integration Test Runner"
echo "═══════════════════════════════════════"

echo "► Starting test Docker services..."
docker compose -f docker-compose.test.yml up -d

echo "► Waiting for services to be healthy..."
timeout 60 bash -c '
  until docker inspect hazardgraph-neo4j-test \
    --format="{{.State.Health.Status}}" 2>/dev/null | grep -q healthy; do
    echo "  Waiting for Neo4j test..."; sleep 3;
  done
'
timeout 30 bash -c '
  until docker inspect hazardgraph-postgres-test \
    --format="{{.State.Health.Status}}" 2>/dev/null | grep -q healthy; do
    echo "  Waiting for PostgreSQL test..."; sleep 2;
  done
'
timeout 15 bash -c '
  until docker inspect hazardgraph-redis-test \
    --format="{{.State.Health.Status}}" 2>/dev/null | grep -q healthy; do
    echo "  Waiting for Redis test..."; sleep 1;
  done
'

echo "► Running pytest..."
export $(cat .env.test | xargs)
python -m pytest tests/ \
  -v \
  --tb=short \
  --asyncio-mode=auto \
  -x \
  --color=yes \
  2>&1 | tee tests/last_run.log

EXIT_CODE=${PIPESTATUS[0]}

echo "► Tearing down test services..."
docker compose -f docker-compose.test.yml down

if [ $EXIT_CODE -eq 0 ]; then
  echo "✅ All tests passed."
else
  echo "❌ Tests failed. See tests/last_run.log"
fi
exit $EXIT_CODE