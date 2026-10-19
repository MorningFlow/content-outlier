from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    content_id: str
    full_text: str
    language: str
    duration: Optional[float] = None
    segments: Optional[list[dict[str, Any]]] = None
    hook_text: Optional[str] = None
    breakdown_hook: Optional[str] = None
    breakdown_topic: Optional[str] = None
    breakdown_format: Optional[str] = None
    breakdown_cta: Optional[str] = None
    key_takeaways: Optional[str] = None
    created_at: datetime
