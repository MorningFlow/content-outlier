import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, BigInteger, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class ContentMetric(Base):
    __tablename__ = "content_metrics"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    content_id = Column(String(36), ForeignKey("content.id", ondelete="CASCADE"), nullable=False, index=True)
    recorded_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    # Performance metrics at snapshot time (NULL if not available, NOT zero)
    views = Column(BigInteger, nullable=True)
    likes = Column(Integer, nullable=True)
    comments = Column(Integer, nullable=True)
    shares = Column(Integer, nullable=True)
    saves = Column(Integer, nullable=True)

    # Calculated metrics between snapshots
    view_growth = Column(BigInteger, nullable=True)
    view_velocity = Column(Float, nullable=True)  # views per hour
    engagement_rate = Column(Float, nullable=True)

    # Relationship
    content = relationship("Content", back_populates="metrics")


Index("ix_content_metrics_content_time", ContentMetric.content_id, ContentMetric.recorded_at.desc())
