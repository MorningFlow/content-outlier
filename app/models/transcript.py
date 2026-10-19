import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Text, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    content_id = Column(String(36), ForeignKey("content.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    full_text = Column(Text, nullable=False)
    language = Column(String(10), default="en", nullable=False)
    duration = Column(Float, nullable=True)

    # List of {start: float, end: float, text: str}
    segments = Column(JSON, nullable=True)

    # Intelligence & Breakdown fields for Content Analysis view
    hook_text = Column(Text, nullable=True)
    breakdown_hook = Column(Text, nullable=True)
    breakdown_topic = Column(Text, nullable=True)
    breakdown_format = Column(Text, nullable=True)
    breakdown_cta = Column(Text, nullable=True)
    key_takeaways = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationship
    content = relationship("Content", back_populates="transcript")
