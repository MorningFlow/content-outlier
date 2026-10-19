import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, Text
from sqlalchemy.orm import relationship
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, index=True, nullable=False)
    instagram_id = Column(String(100), nullable=True)
    profile_name = Column(String(255), nullable=True)
    profile_image = Column(String(1024), nullable=True)
    followers = Column(Integer, nullable=True)
    status = Column(String(50), default="active", nullable=False)  # active, paused, error, rate_limited
    last_scraped_at = Column(DateTime(timezone=True), nullable=True)
    scrape_error = Column(Text, nullable=True)
    rate_limited_until = Column(DateTime(timezone=True), nullable=True)

    # Computed historical baseline
    baseline_views_median = Column(Float, nullable=True)
    baseline_engagement_rate = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    contents = relationship("Content", back_populates="competitor", cascade="all, delete-orphan")
    jobs = relationship("ScrapeJob", back_populates="competitor", cascade="all, delete-orphan")
