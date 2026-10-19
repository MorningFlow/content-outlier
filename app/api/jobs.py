from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.api.deps import get_db
from app.models.job import ScrapeJob, ProcessingJob
from app.schemas.job import JobResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("", response_model=list[JobResponse])
def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List recent background jobs and their current execution statuses."""
    query = db.query(ScrapeJob)
    if status_filter:
        query = query.filter(ScrapeJob.status == status_filter)
    jobs = query.order_by(desc(ScrapeJob.created_at)).limit(limit).all()
    return [JobResponse.model_validate(j) for j in jobs]


@router.get("/{id}", response_model=JobResponse)
def get_job(id: str, db: Session = Depends(get_db)):
    """Get the current status of a background scrape or processing job."""
    scrape_job = db.query(ScrapeJob).filter(ScrapeJob.id == id).first()
    if scrape_job:
        return JobResponse.model_validate(scrape_job)

    proc_job = db.query(ProcessingJob).filter(ProcessingJob.id == id).first()
    if proc_job:
        return JobResponse.model_validate(proc_job)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
