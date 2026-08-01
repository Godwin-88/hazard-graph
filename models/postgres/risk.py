"""HazardGraph — RiskHistory SQLAlchemy model.

Stores periodic risk score snapshots for trend analysis.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    Float,
    Integer,
    String,
    Text,
    DateTime,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from db.postgres_client import Base


class RiskHistory(Base):
    __tablename__ = "risk_history"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    region_id = Column(String(100), nullable=False, index=True)
    score = Column(Float, nullable=False)
    delta = Column(Float, nullable=False, default=0.0)
    component_scores_json = Column(Text, nullable=False)
    vulnerability_multiplier = Column(Float, nullable=False, default=1.0)
    current_regime = Column(String(50), nullable=False, default="Baseline")
    computed_at = Column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        Index("ix_risk_history_region_computed", "region_id", "computed_at"),
    )