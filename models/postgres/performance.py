"""HazardGraph — ModelPerformance SQLAlchemy model.

Tracks Brier scores, BMA weights, and training timestamps for all
14 quantitative models (M1–M14). This table is consumed by:
  - BMAEngine.load_weights()  — posterior weight computation
  - DataHub model registry    — Brier score + weight metadata sync
  - HazardGraph agent         — model health checks
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    DateTime,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from db.postgres_client import Base


class ModelPerformance(Base):
    __tablename__ = "model_performance"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    model_name = Column(String(100), nullable=False, index=True)
    model_id = Column(String(20), nullable=True)  # e.g. "M1", "M14"
    brier_score = Column(Float, nullable=True)
    bma_weight = Column(Float, nullable=True)
    trained_at = Column(DateTime(timezone=True), nullable=True)
    last_inference_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="active")  # active, needs_retraining, retired
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_model_performance_model_name", "model_name"),
        Index("ix_model_performance_model_id", "model_id"),
    )