from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict
from app.schemas.metric import ContentMetricResponse
from app.schemas.transcript import TranscriptResponse


class ContentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    competitor_id: str
    instagram_username: str
    instagram_profile_id: Optional[str] = None
    post_id: Optional[str] = None
    shortcode: str
    instagram_url: str
    content_type: str
    published_at: datetime
    caption: Optional[str] = None
    hashtags: Optional[list[str]] = None
    mentions: Optional[list[str]] = None
    thumbnail_url: Optional[str] = None
    thumbnail_path: Optional[str] = None
    video_url: Optional[str] = None
    video_path: Optional[str] = None
    video_duration: Optional[float] = None

    # Available performance metrics (None if unavailable, NEVER 0 fabricated)
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    share_count: Optional[int] = None
    save_count: Optional[int] = None

    first_discovered_at: datetime
    last_scraped_at: datetime

    # Outlier Intelligence
    is_outlier: bool
    outlier_score: float
    view_multiplier: Optional[float] = None
    engagement_rate: Optional[float] = None
    view_velocity: Optional[float] = None
    outlier_reasons: Optional[dict[str, Any]] = None

    download_status: str
    transcription_status: str
    created_at: datetime
    updated_at: datetime


class ContentDetailResponse(ContentResponse):
    metrics: list[ContentMetricResponse] = []
    transcript: Optional[TranscriptResponse] = None
