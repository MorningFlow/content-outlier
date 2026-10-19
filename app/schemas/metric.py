from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ContentMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    content_id: str
    recorded_at: datetime
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    saves: Optional[int] = None
    view_growth: Optional[int] = None
    view_velocity: Optional[float] = None
    engagement_rate: Optional[float] = None
