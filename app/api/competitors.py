from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.competitor_service import CompetitorService
from app.schemas.competitor import CompetitorCreate, CompetitorUpdate, CompetitorResponse
from app.schemas.job import JobResponse

router = APIRouter(prefix="/competitors", tags=["Competitors"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
def add_competitor(data: CompetitorCreate, db: Session = Depends(get_db)):
    """Add a new Instagram competitor. Automatically queues initial profile sync."""
    service = CompetitorService(db)
    competitor, job = service.create_competitor(data)
    return {
        "competitor": competitor,
        "job": JobResponse.model_validate(job),
        "message": f"Competitor @{competitor.username} added and initial synchronization queued."
    }


@router.get("", response_model=list[CompetitorResponse])
def list_competitors(db: Session = Depends(get_db)):
    """List all tracked competitors with follower and content counts."""
    service = CompetitorService(db)
    return service.list_competitors()


@router.get("/{id}", response_model=CompetitorResponse)
def get_competitor(id: str, db: Session = Depends(get_db)):
    """Retrieve details for a single competitor."""
    service = CompetitorService(db)
    competitor = service.get_by_id(id)
    if not competitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")
    return CompetitorResponse.model_validate(competitor)


@router.patch("/{id}", response_model=CompetitorResponse)
def update_competitor(id: str, data: CompetitorUpdate, db: Session = Depends(get_db)):
    """Update competitor settings (e.g. status active/paused, profile name)."""
    service = CompetitorService(db)
    updated = service.update_competitor(id, data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")
    return updated


@router.delete("/{id}", status_code=status.HTTP_200_OK)
def delete_competitor(id: str, db: Session = Depends(get_db)):
    """Remove a competitor from monitoring."""
    service = CompetitorService(db)
    success = service.delete_competitor(id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")
    return {"message": "Competitor deleted successfully"}


@router.post("/{id}/sync", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_competitor_sync(id: str, db: Session = Depends(get_db)):
    """Manually triggers an on-demand profile sync job for a competitor."""
    service = CompetitorService(db)
    competitor = service.get_by_id(id)
    if not competitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")

    job = service.queue_sync_job(id, job_type="incremental_profile_sync")
    return JobResponse.model_validate(job)


@router.post("/sync-all", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
def trigger_all_competitors_sync(db: Session = Depends(get_db)):
    """Queues incremental sync jobs for every active competitor at once.

    Called automatically when the platform is opened so scraping is driven by
    user visits rather than a background cron schedule.
    Skips competitors that already have a queued or running job.
    """
    service = CompetitorService(db)
    competitors = service.list_competitors()
    queued = []
    skipped = []
    for comp in competitors:
        if getattr(comp, "status", "active") not in ("active", None):
            skipped.append(comp.username)
            continue
        # Don't double-queue if already running/queued
        active_status = getattr(comp.active_job, "status", None) if comp.active_job else None
        if active_status in ("queued", "running"):
            skipped.append(comp.username)
            continue
        try:
            service.queue_sync_job(comp.id, job_type="incremental_profile_sync")
            queued.append(comp.username)
        except Exception:
            skipped.append(comp.username)

    return {
        "queued": queued,
        "skipped": skipped,
        "message": f"Queued {len(queued)} sync job(s).",
    }


@router.post("/{id}/ingest", response_model=dict, status_code=status.HTTP_200_OK)
def ingest_competitor_posts(id: str, payload: dict, db: Session = Depends(get_db)):
    """Accepts bulk scraped post data from the local scraping agent.

    The local agent runs on the user's residential machine, scrapes Instagram
    from their IP (bypassing datacenter blocks), then pushes results here.

    Payload:
        {
          "profile": { "instagram_id": str, "profile_name": str,
                       "profile_image": str|null, "followers": int|null },
          "posts": [ { ...content fields... } ]
        }
    """
    from app.services.content_service import ContentService
    from app.models.competitor import Competitor
    from datetime import datetime, timezone

    competitor = db.query(Competitor).filter(Competitor.id == id).first()
    if not competitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")

    profile = payload.get("profile") or {}
    if profile.get("instagram_id"):
        competitor.instagram_id = profile["instagram_id"]
    if profile.get("profile_name"):
        competitor.profile_name = profile["profile_name"]
    if profile.get("profile_image"):
        competitor.profile_image = profile["profile_image"]
    if profile.get("followers") is not None:
        competitor.followers = profile["followers"]
    competitor.status = "active"
    competitor.scrape_error = None
    competitor.last_scraped_at = datetime.now(timezone.utc)
    db.commit()

    posts = payload.get("posts") or []
    if posts:
        content_service = ContentService(db)
        content_service.ingest_scraped_items(id, posts)

    return {
        "ingested": len(posts),
        "message": f"Ingested {len(posts)} posts for @{competitor.username}.",
    }
