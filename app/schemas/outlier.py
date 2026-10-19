from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class OutlierCardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    shortcode: str
    instagram_url: str
    username: str
    caption: Optional[str] = None
    thumbnail_url: Optional[str] = None
    video_url: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    published_at: datetime
    age_days: int
    outlier_score: float
    view_multiplier: Optional[float] = None
    baseline_views: Optional[int] = None
    engagement_rate: Optional[float] = None
    view_velocity: Optional[float] = None
    outlier_reasons: Optional[dict[str, Any]] = None
    download_status: str
    transcription_status: str


class OutlierListResponse(BaseModel):
    items: list[OutlierCardResponse]
    total: int
    page: int
    limit: int
