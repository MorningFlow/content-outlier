from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.schemas.outlier import OutlierCardResponse


class DashboardResponse(BaseModel):
    competitors_count: int
    content_tracked_count: int
    outliers_found_count: int
    last_updated: Optional[datetime] = None
    last_updated_human: str
    top_outlier: Optional[OutlierCardResponse] = None
    recent_outliers: list[OutlierCardResponse] = []
