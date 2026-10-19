from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator, computed_field
from app.schemas.job import JobResponse


class CompetitorBase(BaseModel):
    username: str

    @field_validator("username")
    @classmethod
    def clean_username(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Instagram username or URL cannot be empty")
        if "instagram.com" in clean or "/" in clean:
            return clean
        return clean.lstrip("@").lower()


class CompetitorCreate(CompetitorBase):
    pass


class CompetitorUpdate(BaseModel):
    status: Optional[str] = None  # active, paused
    profile_name: Optional[str] = None


class CompetitorResponse(CompetitorBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    instagram_id: Optional[str] = None
    profile_name: Optional[str] = None
    profile_image: Optional[str] = None
    followers: Optional[int] = None
    status: str
    last_scraped_at: Optional[datetime] = None
    scrape_error: Optional[str] = None
    baseline_views_median: Optional[float] = None
    baseline_engagement_rate: Optional[float] = None
    content_count: int = 0
    active_job: Optional[JobResponse] = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def is_active(self) -> bool:
        return self.status == "active"
