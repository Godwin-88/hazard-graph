"""HazardGraph — Alert, AlertDelivery, AlertResponse SQLAlchemy models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from db.postgres_client import Base

import enum


class AlertStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    ACKNOWLEDGED = "acknowledged"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(String(100), nullable=False, index=True)
    language = Column(String(10), nullable=False, default="en")
    message_text = Column(Text, nullable=False)
    risk_score_at_trigger = Column(Float, nullable=False, default=0.0)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    status = Column(String(20), nullable=False, default=AlertStatus.PENDING.value)
    kelly_priority = Column(Float, nullable=False, default=0.0)
    sent_count = Column(Integer, nullable=False, default=0)
    delivered_count = Column(Integer, nullable=False, default=0)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String(100), nullable=True)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    deliveries = relationship("AlertDelivery", back_populates="alert", cascade="all, delete-orphan")
    responses = relationship("AlertResponse", back_populates="alert", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_alerts_region_status", "region_id", "status"),
    )


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id = Column(UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False)
    channel = Column(String(50), nullable=False)  # sms, email, push, voice
    recipient = Column(String(255), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    alert = relationship("Alert", back_populates="deliveries")

    __table_args__ = (
        Index("ix_alert_deliveries_alert_id", "alert_id"),
    )


class AlertResponse(Base):
    __tablename__ = "alert_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id = Column(UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    response_type = Column(String(50), nullable=False)  # acknowledged, action_taken, false_alarm, feedback
    response_text = Column(Text, nullable=True)
    responded_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    alert = relationship("Alert", back_populates="responses")

    __table_args__ = (
        Index("ix_alert_responses_alert_id", "alert_id"),
    )