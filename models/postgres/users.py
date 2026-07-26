"""HazardGraph — User SQLAlchemy model."""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID

from db.postgres_client import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="viewer")  # admin, analyst, viewer
    is_active = Column(Boolean, nullable=False, default=True)
    preferred_language = Column(String(10), nullable=False, default="en")
    phone = Column(String(50), nullable=True)
    region_focus = Column(String(100), nullable=True)  # primary region of interest
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_users_role", "role"),
    )