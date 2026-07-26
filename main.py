"""HazardGraph — FastAPI application entry point.

Lifespan context manager handles startup/shutdown of all
database connections, schema validation, and scheduler.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from db.neo4j_client import neo4j_client
from db.postgres_client import create_all_tables, close_postgres
from db.redis_client import redis_client
from graph.schema_validator import validate_schema
from scheduler.jobs import register_jobs, start_scheduler, stop_scheduler

# ── Logging ────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Lifespan ───────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup → yield → shutdown."""
    logger.info("Starting HazardGraph v%s", settings.app_version)

    # ── Startup ──────────────────────────────────────────
    startup_errors = []

    # 1. Connect Neo4j
    try:
        await neo4j_client.connect()
        logger.info("Neo4j connected successfully")
    except Exception as exc:
        logger.error("Neo4j connection failed: %s", exc)
        startup_errors.append(f"Neo4j: {exc}")

    # 2. Create PostgreSQL tables
    try:
        await create_all_tables()
        logger.info("PostgreSQL tables created/verified")
    except Exception as exc:
        logger.error("PostgreSQL table creation failed: %s", exc)
        startup_errors.append(f"PostgreSQL: {exc}")

    # 3. Connect Redis
    try:
        await redis_client.connect()
        logger.info("Redis connected successfully")
    except Exception as exc:
        logger.error("Redis connection failed: %s", exc)
        startup_errors.append(f"Redis: {exc}")

    # 4. Validate Neo4j schema
    try:
        schema_result = await validate_schema()
        if not schema_result["valid"]:
            logger.warning(
                "Neo4j schema validation incomplete. Missing labels: %s, Missing rels: %s",
                schema_result["missing_labels"],
                schema_result["missing_relationships"],
            )
        else:
            logger.info("Neo4j schema validated successfully")
    except Exception as exc:
        logger.error("Schema validation failed: %s", exc)
        startup_errors.append(f"Schema: {exc}")

    # 5. Register and start scheduler
    try:
        register_jobs()
        start_scheduler()
        logger.info("Scheduler initialised")
    except Exception as exc:
        logger.error("Scheduler initialisation failed: %s", exc)
        startup_errors.append(f"Scheduler: {exc}")

    if startup_errors:
        logger.warning("Startup completed with %d error(s): %s", len(startup_errors), startup_errors)
    else:
        logger.info("Startup complete — all systems connected")

    yield  # Application runs here

    # ── Shutdown ─────────────────────────────────────────
    logger.info("Shutting down HazardGraph...")

    try:
        stop_scheduler()
    except Exception as exc:
        logger.warning("Scheduler shutdown error: %s", exc)

    try:
        await neo4j_client.close()
    except Exception as exc:
        logger.warning("Neo4j shutdown error: %s", exc)

    try:
        await close_postgres()
    except Exception as exc:
        logger.warning("PostgreSQL shutdown error: %s", exc)

    try:
        await redis_client.close()
    except Exception as exc:
        logger.warning("Redis shutdown error: %s", exc)

    logger.info("Shutdown complete")


# ── FastAPI App ────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS Middleware ────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────
from api.routers.health import router as health_router
from api.routers.lineage import router as lineage_router
from api.routers.graph import router as graph_router
from api.routers.risk import router as risk_router
from api.routers.forecast import router as forecast_router

app.include_router(health_router, prefix="/api/v1")
app.include_router(lineage_router, prefix="/api/v1")
app.include_router(graph_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(forecast_router, prefix="/api/v1")


# ── Root endpoint ──────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/v1/health",
    }