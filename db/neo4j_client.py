"""HazardGraph — Async Neo4j driver singleton with health check."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession, AsyncManagedTransaction

from config.settings import settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Async Neo4j driver wrapper with connection pooling."""

    def __init__(self) -> None:
        self._driver: Optional[AsyncDriver] = None

    async def connect(self) -> None:
        """Initialise the Neo4j async driver."""
        if self._driver is not None:
            return
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_lifetime=3600,
            max_connection_pool_size=50,
            connection_acquisition_timeout=30,
        )
        # Verify connectivity
        await self._driver.verify_connectivity()
        logger.info("Neo4j connected to %s", settings.neo4j_uri)

    async def close(self) -> None:
        """Close the driver and all pooled connections."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager yielding a Neo4j async session."""
        if self._driver is None:
            raise RuntimeError("Neo4j driver not initialised. Call connect() first.")
        async with self._driver.session() as session:
            yield session

    async def execute_read(self, query: str, parameters: dict = None) -> list:
        """Execute a read transaction and return records."""
        async with self.get_session() as session:
            result = await session.execute_read(
                lambda tx: self._run_query(tx, query, parameters or {})
            )
            return result

    async def execute_write(self, query: str, parameters: dict = None) -> list:
        """Execute a write transaction and return records."""
        async with self.get_session() as session:
            result = await session.execute_write(
                lambda tx: self._run_query(tx, query, parameters or {})
            )
            return result

    @staticmethod
    async def _run_query(tx: AsyncManagedTransaction, query: str, parameters: dict) -> list:
        result = await tx.run(query, parameters)
        return [record.data() for record in await result.fetch()]

    async def health_check(self) -> dict:
        """Check Neo4j connectivity and return node count."""
        connected = False
        node_count = 0
        try:
            if self._driver is None:
                await self.connect()
            await self._driver.verify_connectivity()
            connected = True
            result = await self.execute_read("MATCH (n) RETURN count(n) AS count")
            node_count = result[0]["count"] if result else 0
        except Exception as exc:
            logger.warning("Neo4j health check failed: %s", exc)
        return {"connected": connected, "node_count": node_count}


# ── FastAPI dependency ────────────────────────────────


async def get_neo4j_session():
    """FastAPI dependency yielding a Neo4j session from the singleton client."""
    async with neo4j_client.get_session() as session:
        yield session


# Singleton
neo4j_client = Neo4jClient()
