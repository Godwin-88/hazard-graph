"""HazardGraph — JobRun SQLAlchemy model for scheduler audit trail."""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, Integer, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from db.postgres_client import Base


class JobRun(Base):
    __tablename__ = "job_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_name = Column(String(255), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="running")  # running, completed, failed
    started_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    records_processed = Column(Integer, nullable=True, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_job_runs_job_name_status", "job_name", "status"),
        Index("ix_job_runs_started_at", "started_at"),
    )


class JobErrorLog(Base):
    """Structured error log for a failed job run.

    Captures the full traceback, error type, and (for DAG runs) the
    specific node that failed, so the UI can render a detailed,
    actionable error view rather than a single truncated string.
    """

    __tablename__ = "job_error_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_name = Column(String(255), nullable=False)
    error_type = Column(String(100), nullable=False)  # e.g. TimeoutError, ValueError
    error_message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)  # full formatted traceback
    node_name = Column(String(255), nullable=True)  # DAG node that failed, if any
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # NOTE: Indexes for job_error_logs (ix_job_error_logs_run_id,
    # ix_job_error_logs_job_name) are intentionally NOT declared here.
    # They are created idempotently by ensure_schema_migrations() in
    # db/postgres_client.py. Declaring them in the ORM model causes
    # Base.metadata.create_all() to attempt re-creating them on every
    # startup (SQLAlchemy does not check for existing indexes), which
    # raises DuplicateTableError on existing deployments.
