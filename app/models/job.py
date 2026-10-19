import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_type = Column(String(50), nullable=False, index=True)
    # Types: initial_profile_sync, incremental_profile_sync, content_metadata_update, metric_snapshot

    status = Column(String(30), default="queued", nullable=False, index=True)
    # Statuses: queued, running, completed, failed

    competitor_id = Column(String(36), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=True, index=True)
    content_id = Column(String(36), ForeignKey("content.id", ondelete="CASCADE"), nullable=True, index=True)

    payload = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)

    progress_percent = Column(Integer, default=0, nullable=False)
    progress_stage = Column(String(255), nullable=True)

    scheduled_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    competitor = relationship("Competitor", back_populates="jobs")
    content = relationship("Content", back_populates="jobs")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_type = Column(String(50), nullable=False, index=True)
    # Types: video_download, transcription

    status = Column(String(30), default="queued", nullable=False, index=True)
    # Statuses: queued, running, completed, failed

    content_id = Column(String(36), ForeignKey("content.id", ondelete="CASCADE"), nullable=False, index=True)

    payload = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)

    progress_percent = Column(Integer, default=0, nullable=False)
    progress_stage = Column(String(255), nullable=True)

    scheduled_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    content = relationship("Content")


Index("ix_scrape_jobs_status_sched", ScrapeJob.status, ScrapeJob.scheduled_at)
Index("ix_processing_jobs_status_sched", ProcessingJob.status, ProcessingJob.scheduled_at)
