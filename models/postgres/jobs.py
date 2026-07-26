"""HazardGraph — JobRun SQLAlchemy model for scheduler audit trail."""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, Integer, Index
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