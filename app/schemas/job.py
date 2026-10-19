from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_type: str
    status: str
    competitor_id: Optional[str] = None
    content_id: Optional[str] = None
    attempts: int
    max_attempts: int
    progress_percent: int = 0
    progress_stage: Optional[str] = None
    error_message: Optional[str] = None
    scheduled_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
