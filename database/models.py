from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from .db import Base


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    source_type = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    metric_name = Column(String, nullable=False)
    metric_value = Column(Float)
    classification = Column(String)
    confidence = Column(Float)
    reason = Column(Text)
    escalated = Column(Boolean, default=False)
    raw_data = Column(JSON)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    event_id = Column(Integer)
    alert_text = Column(Text)
    runbook_context = Column(Text)
    email_sent_to = Column(String)
    email_sent_at = Column(DateTime(timezone=True))


class Target(Base):
    __tablename__ = "targets"
    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String)
    name = Column(String, unique=True, index=True)
    enabled = Column(Boolean, default=True)
    check_interval_seconds = Column(Integer, default=300)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
