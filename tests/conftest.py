"""
Pytest fixtures for HazardGraph integration tests.
All fixtures connect to Docker test services.
Run: docker compose -f docker-compose.test.yml up -d
     then: pytest tests/
"""

import pytest
import pytest_asyncio
import asyncio
import os
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from neo4j import AsyncGraphDatabase
import redis.asyncio as aioredis

# Set test environment variables BEFORE any imports that load settings
# This ensures the global singletons connect to test containers
os.environ.setdefault('APP_ENV', 'test')
os.environ['NEO4J_URI'] = os.getenv('NEO4J_URI', 'bolt://localhost:7688')
os.environ['NEO4J_USER'] = os.getenv('NEO4J_USER', 'neo4j')
os.environ['NEO4J_PASSWORD'] = os.getenv('NEO4J_PASSWORD', 'testpassword')
os.environ['POSTGRES_DSN'] = os.getenv(
    'POSTGRES_URL',
    'postgresql+asyncpg://hazardgraph_test:testpassword@localhost:5433/hazardgraph_test'
)
os.environ['REDIS_URL'] = os.getenv('REDIS_URL', 'redis://localhost:6380')


@pytest_asyncio.fixture(scope='session', loop_scope='session')
async def neo4j_driver():
    """Connect to test Neo4j container.

    Also connects the global neo4j_client singleton so that functions
    using it directly (e.g., write_causal_edges, compute_risk_scores,
    ingest_icpac_rss) work correctly with the test container.
    """
    # Connect the global neo4j_client singleton to the test container
    from db.neo4j_client import neo4j_client
    await neo4j_client.connect()

    driver = AsyncGraphDatabase.driver(
        os.getenv('NEO4J_URI', 'bolt://localhost:7688'),
        auth=(os.getenv('NEO4J_USERNAME', 'neo4j'),
              os.getenv('NEO4J_PASSWORD', 'testpassword'))
    )
    # Run schema migration
    async with driver.session() as session:
        migration_path = 'migrations/001_schema.cypher'
        if os.path.exists(migration_path):
            with open(migration_path) as f:
                migration = f.read()
            for stmt in migration.split(';'):
                stmt = stmt.strip()
                if stmt:
                    try:
                        await session.run(stmt)
                    except Exception as e:
                        if 'already exists' not in str(e).lower():
                            print(f"  Migration warning: {e}")
    yield driver
    await driver.close()


@pytest_asyncio.fixture(scope='session', loop_scope='session')
async def postgres_session(neo4j_driver):
    """Create all tables and return session factory."""
    engine = create_async_engine(
        os.getenv('POSTGRES_URL',
                   'postgresql+asyncpg://hazardgraph_test:testpassword'
                   '@localhost:5433/hazardgraph_test'),
        echo=False
    )
    from models.postgres.base import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope='session', loop_scope='session')
async def redis_client():
    """Connect to test Redis container."""
    client = await aioredis.from_url(
        os.getenv('REDIS_URL', 'redis://localhost:6380'),
        encoding='utf-8',
        decode_responses=True
    )
    yield client
    await client.flushall()    # clean slate after tests
    await client.close()


@pytest_asyncio.fixture(scope='session', loop_scope='session')
async def api_client(neo4j_driver, postgres_session, redis_client):
    """FastAPI test client with overridden DB dependencies.

    Also connects the global singletons (neo4j_client, redis_client)
    to the test containers so that functions using them directly
    (e.g., health check, write_causal_edges, ingest_icpac_rss)
    work correctly.
    """
    from main import app
    from db.neo4j_client import get_neo4j_session, neo4j_client
    from db.postgres_client import get_db
    from db.redis_client import get_redis, redis_client as global_redis

    # Connect global singletons to test containers
    # (they use settings which now point to test containers via env vars)
    from config.settings import settings
    # Force reconnect by setting environment and re-importing
    await neo4j_client.connect()
    await global_redis.connect()

    # Override dependencies to use test containers
    async def override_neo4j():
        async with neo4j_driver.session() as session:
            yield session

    async def override_postgres():
        yield postgres_session

    async def override_redis():
        yield redis_client

    app.dependency_overrides[get_neo4j_session] = override_neo4j
    app.dependency_overrides[get_db] = override_postgres
    app.dependency_overrides[get_redis] = override_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        yield client

    app.dependency_overrides.clear()
    await neo4j_client.close()
    await global_redis.close()


@pytest_asyncio.fixture
async def auth_headers(api_client):
    """Get JWT token for test admin user.

    Uses a separate database session to avoid conflicts with
    the shared postgres_session fixture used by get_db dependency.
    """
    # First try logging in
    response = await api_client.post('/api/v1/auth/login', json={
        'username': 'admin',
        'password': 'HazardGraph2026!'
    })

    if response.status_code != 200:
        # Create the admin user using a fresh session
        from db.postgres_client import async_session_factory
        from auth.password_service import hash_password
        from models.postgres.users import User
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.username == 'admin')
            )
            if not result.scalar_one_or_none():
                session.add(User(
                    username='admin',
                    email='admin@hazardgraph.io',
                    hashed_password=hash_password('HazardGraph2026!'),
                    name='Admin User',
                    role='admin',
                    is_active=True
                ))
                await session.commit()

        response = await api_client.post('/api/v1/auth/login', json={
            'username': 'admin',
            'password': 'HazardGraph2026!'
        })

    token = response.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def sample_risk_score():
    """Realistic RegionRiskScore for unit tests."""
    from risk.scoring_service import RegionRiskScore
    return RegionRiskScore(
        region_id='kenya',
        name='Kenya',
        country='kenya',
        score=67.3,
        delta=12.1,
        components={
            'rainfall': 0.72,
            'food': 0.45,
            'ipc': 0.60,
            'sde': 0.55,
            'network': 0.38
        },
        vulnerability_multiplier=1.43,
        current_regime='DroughtOnset',
        alert_triggered=True
    )


@pytest.fixture
def sample_rainfall_series():
    """28 weeks of synthetic SPI data for model tests."""
    import numpy as np
    np.random.seed(42)
    # Simulate drought onset: starts near 0, drifts negative
    return list(np.cumsum(np.random.normal(-0.08, 0.3, 28)))