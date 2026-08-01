"""HazardGraph — SQLAlchemy 2.0 async engine, Base, get_db dependency."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config.settings import settings

logger = logging.getLogger(__name__)

# Ensure the DSN uses the asyncpg dialect; if the user supplied a plain
# postgresql:// URL, convert it to postgresql+asyncpg:// automatically.
dsn = settings.postgres_dsn
if dsn and "+" not in dsn.split("://")[0]:
    dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    dsn,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0},
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_all_tables() -> None:
    """Create all tables defined in models/postgres/."""
    from models.postgres.base import Base  # noqa: F401 — ensures all models are imported
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("PostgreSQL tables created / verified")


async def ensure_schema_migrations() -> None:
    """Apply idempotent lightweight migrations for existing deployments.

    create_all() does not alter existing tables, so schema changes to
    pre-existing deployments must be applied explicitly here. Each step
    is guarded so it can safely run on every startup.
    """
    async with engine.begin() as conn:
        # risk_history.id previously had no server-side default, so raw
        # SQL inserts (scoring_service) produced NULL → NotNullViolationError.
        # Add a DB-level default for both fresh and existing tables.
        await conn.execute(
            text(
                "ALTER TABLE IF EXISTS risk_history "
                "ALTER COLUMN id SET DEFAULT gen_random_uuid()"
            )
        )
        logger.info("Ensured risk_history.id server default")

        # risk_history.delta default is enforced only by the app for raw
        # inserts; backfill a server default too for robustness.
        await conn.execute(
            text(
                "ALTER TABLE IF EXISTS risk_history "
                "ALTER COLUMN delta SET DEFAULT 0.0"
            )
        )
        logger.info("Ensured risk_history.delta server default")

        # job_runs.id is a UUID with only a Python-side default, so raw
        # SQL inserts (pipeline router) produced NULL → NotNullViolationError.
        # Add a DB-level default for both fresh and existing tables.
        await conn.execute(
            text(
                "ALTER TABLE IF EXISTS job_runs "
                "ALTER COLUMN id SET DEFAULT gen_random_uuid()"
            )
        )
        logger.info("Ensured job_runs.id server default")

        # alerts.approved_at / approved_by / dispatched_at / rejection_reason
        # are queried by the alerts router but were missing from existing
        # deployments' alerts table → UndefinedColumnError. Add them
        # idempotently so existing tables are upgraded on startup.
        await conn.execute(
            text(
                "ALTER TABLE IF EXISTS alerts "
                "ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE IF EXISTS alerts "
                "ADD COLUMN IF NOT EXISTS approved_by VARCHAR(100)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE IF EXISTS alerts "
                "ADD COLUMN IF NOT EXISTS dispatched_at TIMESTAMPTZ"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE IF EXISTS alerts "
                "ADD COLUMN IF NOT EXISTS rejection_reason TEXT"
            )
        )
        # alerts.id is a UUID with only a Python-side default; ensure a
        # DB-level default so raw SQL inserts are safe.
        await conn.execute(
            text(
                "ALTER TABLE IF EXISTS alerts "
                "ALTER COLUMN id SET DEFAULT gen_random_uuid()"
            )
        )
        logger.info("Ensured alerts dispatch/approval columns + id server default")

        # alerts.status was previously a native Postgres enum (alertstatus),
        # which rejects plain-string comparisons in raw SQL (e.g. WHERE
        # status = 'pending'). Convert it to VARCHAR(20) so the router's
        # text() queries work. Drop any enum-typed default first, since
        # Postgres refuses to re-type a column whose default still references
        # the enum type.
        await conn.execute(
            text("ALTER TABLE IF EXISTS alerts ALTER COLUMN status DROP DEFAULT")
        )
        await conn.execute(
            text(
                "ALTER TABLE IF EXISTS alerts "
                "ALTER COLUMN status TYPE VARCHAR(20) "
                "USING status::text"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE IF EXISTS alerts "
                "ALTER COLUMN status SET DEFAULT 'pending'"
            )
        )
        logger.info("Ensured alerts.status is VARCHAR(20)")


async def close_postgres() -> None:
    """Dispose of the engine."""
    await engine.dispose()
    logger.info("PostgreSQL engine disposed")