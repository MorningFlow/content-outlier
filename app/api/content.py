from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from app.api.deps import get_db
from app.models.content import Content
from app.models.competitor import Competitor
from app.services.content_service import ContentService
from app.schemas.content import ContentResponse, ContentDetailResponse
from app.schemas.metric import ContentMetricResponse
from app.schemas.transcript import TranscriptResponse

router = APIRouter(prefix="/content", tags=["Content"])


@router.get("", response_model=list[ContentResponse])
def list_content(
    competitor: Optional[str] = Query(None, description="Filter by competitor username or ID"),
    range: Optional[str] = Query("all", description="Date range: 30d, 60d, 90d, or all"),
    search: Optional[str] = Query(None, description="Search term for caption or hashtags"),
    sort: Optional[str] = Query("published", description="Sort by: published, views, likes, shares, score"),
    order: Optional[str] = Query("desc", description="Sort order: desc or asc"),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List tracked content items across monitored competitors with chronological sorting and filtering."""
    query = db.query(Content)

    if competitor:
        clean = competitor.strip().lstrip("@").lower()
        comp = db.query(Competitor).filter((Competitor.username == clean) | (Competitor.id == competitor)).first()
        if comp:
            query = query.filter(Content.competitor_id == comp.id)
        else:
            return []

    if range and range != "all":
        now = datetime.now(timezone.utc)
        days = 30
        if range == "7d":
            days = 7
        elif range == "14d":
            days = 14
        elif range == "30d":
            days = 30
        elif range == "60d":
            days = 60
        elif range == "90d":
            days = 90
        elif range.endswith("d") and range[:-1].isdigit():
            days = int(range[:-1])
        cutoff = now - timedelta(days=days)
        query = query.filter(Content.published_at >= cutoff)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(Content.caption.ilike(term))

    # Sorting
    sort_column = Content.published_at
    if sort == "views":
        sort_column = Content.view_count
    elif sort == "likes":
        sort_column = Content.like_count
    elif sort == "shares":
        sort_column = Content.share_count
    elif sort == "score":
        sort_column = Content.outlier_score

    if order == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    offset = (page - 1) * limit
    items = query.offset(offset).limit(limit).all()
    return [ContentResponse.model_validate(item) for item in items]


@router.get("/{id}", response_model=ContentDetailResponse)
def get_content_detail(id: str, db: Session = Depends(get_db)):
    """Retrieve full content details including transcript and performance breakdown."""
    service = ContentService(db)
    content = service.get_content_by_id(id)
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")

    metrics = service.get_metrics_history(id)
    transcript = service.get_transcript(id)

    detail = ContentDetailResponse.model_validate(content)
    detail.metrics = [ContentMetricResponse.model_validate(m) for m in metrics]
    detail.transcript = TranscriptResponse.model_validate(transcript) if transcript else None
    return detail


@router.get("/{id}/metrics", response_model=list[ContentMetricResponse])
def get_content_metrics(id: str, db: Session = Depends(get_db)):
    """Retrieve historical metric snapshots for performance growth and velocity tracking."""
    service = ContentService(db)
    content = service.get_content_by_id(id)
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")

    metrics = service.get_metrics_history(id)
    return [ContentMetricResponse.model_validate(m) for m in metrics]


@router.get("/{id}/transcript", response_model=TranscriptResponse)
def get_content_transcript(id: str, db: Session = Depends(get_db)):
    """Retrieve timestamped transcript and hook breakdown for a Reel."""
    service = ContentService(db)
    content = service.get_content_by_id(id)
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")

    transcript = service.get_transcript(id)
    if not transcript:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not available yet for this content")

    return TranscriptResponse.model_validate(transcript)


@router.post("/{id}/download", status_code=status.HTTP_202_ACCEPTED)
def request_offline_download(id: str, db: Session = Depends(get_db)):
    """On-demand: Flag a specific content item for local video download.
    Videos are NOT downloaded by default (zero disk bloat). Use this endpoint
    to explicitly queue a download for offline analysis of a specific Reel."""
    from app.models.job import ProcessingJob
    from datetime import datetime, timezone

    service = ContentService(db)
    content = service.get_content_by_id(id)
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")

    if content.download_status == "completed":
        return {"message": "Video already downloaded locally.", "download_status": "completed"}

    if content.download_status == "pending":
        return {"message": "Download already queued.", "download_status": "pending"}

    now = datetime.now(timezone.utc)
    content.download_status = "pending"
    dl_job = ProcessingJob(
        job_type="video_download",
        status="queued",
        content_id=content.id,
        scheduled_at=now,
        payload={"instagram_url": content.instagram_url, "video_url": content.video_url},
    )
    db.add(dl_job)
    db.commit()
    return {
        "message": "Video download queued for offline analysis.",
        "content_id": id,
        "download_status": "pending",
        "job_id": dl_job.id,
    }


@router.post("/{id}/transcribe", response_model=TranscriptResponse, status_code=status.HTTP_200_OK)
def trigger_transcription(id: str, db: Session = Depends(get_db)):
    """Generate or retrieve timestamped transcript and content breakdown on-demand."""
    from app.services.transcription_service import TranscriptionService

    service = ContentService(db)
    content = service.get_content_by_id(id)
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")

    existing = service.get_transcript(id)
    if existing:
        return TranscriptResponse.model_validate(existing)

    transcription_service = TranscriptionService(db)
    transcript = transcription_service.transcribe_content(id)
    if not transcript:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to transcribe content")

    return TranscriptResponse.model_validate(transcript)

