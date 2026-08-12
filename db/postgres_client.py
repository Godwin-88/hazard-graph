"""HazardGraph — SQLAlchemy 2.0 async engine, Base, get_db dependency."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
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
    """Create all tables defined in models/postgres/.

    SQLAlchemy's create_all(checkfirst=True) checks for table existence but
    NOT for index existence. On an existing deployment (e.g. the remote
    Supabase Postgres), the tables already exist, so create_all skips them
    but still attempts to re-create their indexes, raising
    DuplicateTableError and aborting startup. We catch that here and
    continue so ensure_schema_migrations() can run idempotently.
    """
    from models.postgres.base import Base  # noqa: F401 — ensures all models are imported
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL tables created / verified")
    except ProgrammingError as exc:
        # Duplicate index/table on an existing deployment — safe to ignore.
        logger.warning(
            "create_all skipped existing objects (expected on existing DB): %s",
            exc.orig if hasattr(exc, "orig") else exc,
        )


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

        # model_performance — Brier scores, BMA weights, training timestamps.
        # create_all() may skip this on existing deployments (see note in
        # create_all_tables), so create it idempotently here.
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS model_performance ("
                "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                "  model_name VARCHAR(100) NOT NULL,"
                "  model_id VARCHAR(20),"
                "  brier_score FLOAT,"
                "  bma_weight FLOAT,"
                "  trained_at TIMESTAMPTZ,"
                "  last_inference_at TIMESTAMPTZ,"
                "  status VARCHAR(20) NOT NULL DEFAULT 'active',"
                "  notes TEXT,"
                "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
                "  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                ")"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_model_performance_model_name "
                "ON model_performance(model_name)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_model_performance_model_id "
                "ON model_performance(model_id)"
            )
        )
        logger.info("Ensured model_performance table + indexes")

        # job_error_logs — structured error logging for failed model runs.
        # create_all() creates this for fresh deployments; add it idempotently
        # for existing deployments so the UI can render detailed error views.
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS job_error_logs ("
                "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                "  run_id UUID NOT NULL REFERENCES job_runs(id) ON DELETE CASCADE,"
                "  job_name VARCHAR(255) NOT NULL,"
                "  error_type VARCHAR(100) NOT NULL,"
                "  error_message TEXT NOT NULL,"
                "  traceback TEXT,"
                "  node_name VARCHAR(255),"
                "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                ")"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_job_error_logs_run_id "
                "ON job_error_logs(run_id)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_job_error_logs_job_name "
                "ON job_error_logs(job_name)"
            )
        )
        logger.info("Ensured job_error_logs table + indexes")


async def close_postgres() -> None:
    """Dispose of the engine."""
    await engine.dispose()
    logger.info("PostgreSQL engine disposed")