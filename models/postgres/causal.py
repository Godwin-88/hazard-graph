"""HazardGraph — CausalRun SQLAlchemy model for tracking causal discovery runs."""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, Integer, Float, Index
from sqlalchemy.dialects.postgresql import UUID

from db.postgres_client import Base


class CausalRun(Base):
    __tablename__ = "causal_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_name = Column(String(255), nullable=False)
    method = Column(String(100), nullable=False)  # pcalg, lingam, granger, dagma
    region_id = Column(String(100), nullable=True)
    signal_types = Column(String(500), nullable=True)  # comma-separated list
    num_edges_discovered = Column(Integer, nullable=True, default=0)
    execution_time_seconds = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="running")  # running, completed, failed
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_causal_runs_region_id", "region_id"),
        Index("ix_causal_runs_method", "method"),
    )