import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, BigInteger, Float, Boolean, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Content(Base):
    __tablename__ = "content"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    competitor_id = Column(String(36), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True)

    instagram_username = Column(String(100), nullable=False, index=True)
    instagram_profile_id = Column(String(100), nullable=True)
    post_id = Column(String(100), nullable=True)
    shortcode = Column(String(100), unique=True, index=True, nullable=False)
    instagram_url = Column(String(500), nullable=False)
    content_type = Column(String(50), default="reel", nullable=False)  # reel, video, post
    published_at = Column(DateTime(timezone=True), nullable=False, index=True)

    caption = Column(Text, nullable=True)
    hashtags = Column(JSON, nullable=True)
    mentions = Column(JSON, nullable=True)

    thumbnail_url = Column(String(1024), nullable=True)
    thumbnail_path = Column(String(500), nullable=True)
    video_url = Column(String(1024), nullable=True)
    video_path = Column(String(500), nullable=True)
    video_duration = Column(Float, nullable=True)

    # Core performance metrics (NULL if not available from Instagram, NOT zero)
    view_count = Column(BigInteger, nullable=True)
    like_count = Column(Integer, nullable=True)
    comment_count = Column(Integer, nullable=True)
    share_count = Column(Integer, nullable=True)
    save_count = Column(Integer, nullable=True)

    first_discovered_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_scraped_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Outlier intelligence
    is_outlier = Column(Boolean, default=False, index=True, nullable=False)
    outlier_score = Column(Float, default=1.0, index=True, nullable=False)
    view_multiplier = Column(Float, nullable=True)
    engagement_rate = Column(Float, nullable=True)
    view_velocity = Column(Float, nullable=True)  # views per hour
    outlier_reasons = Column(JSON, nullable=True)  # Explainability metadata

    # Media and processing statuses
    download_status = Column(String(50), default="not_required", nullable=False)  # pending, downloaded, failed, not_required
    transcription_status = Column(String(50), default="not_required", nullable=False)  # pending, completed, failed, not_required

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    competitor = relationship("Competitor", back_populates="contents")
    metrics = relationship("ContentMetric", back_populates="content", cascade="all, delete-orphan", order_by="ContentMetric.recorded_at.desc()")
    transcript = relationship("Transcript", back_populates="content", uselist=False, cascade="all, delete-orphan")
    jobs = relationship("ScrapeJob", back_populates="content", cascade="all, delete-orphan")


Index("ix_content_competitor_published", Content.competitor_id, Content.published_at.desc())
Index("ix_content_outlier_composite", Content.is_outlier, Content.outlier_score.desc())
