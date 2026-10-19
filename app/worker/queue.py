import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.config import settings
from app.models.job import ScrapeJob, ProcessingJob

logger = logging.getLogger(__name__)


class JobQueue:
    """Database-backed transactional job queue with locking and retry support."""

    def __init__(self, db: Session):
        self.db = db

    def acquire_next_job(self) -> Optional[Union[ScrapeJob, ProcessingJob]]:
        """Atomically locks and retrieves the next queued job scheduled to run."""
        now = datetime.now(timezone.utc)
        now_cmp = now.replace(tzinfo=None) if settings.is_sqlite else now

        # First check scrape jobs
        scrape_query = self.db.query(ScrapeJob).filter(
            ScrapeJob.status == "queued",
            or_(ScrapeJob.scheduled_at <= now, ScrapeJob.scheduled_at <= now_cmp),
            ScrapeJob.attempts < ScrapeJob.max_attempts,
        )
        if not settings.is_sqlite:
            # PostgreSQL supports skip locked for non-blocking concurrent workers
            scrape_query = scrape_query.with_for_update(skip_locked=True)

        job = scrape_query.order_by(ScrapeJob.scheduled_at.asc()).first()
        if job:
            job.status = "running"
            job.started_at = now
            job.attempts += 1
            job.progress_percent = max(job.progress_percent or 0, 5)
            if not job.progress_stage or "Queued" in job.progress_stage:
                job.progress_stage = "Job started by worker..."
            self.db.commit()
            return job

        # Next check processing jobs (downloads, transcription)
        proc_query = self.db.query(ProcessingJob).filter(
            ProcessingJob.status == "queued",
            or_(ProcessingJob.scheduled_at <= now, ProcessingJob.scheduled_at <= now_cmp),
            ProcessingJob.attempts < ProcessingJob.max_attempts,
        )
        if not settings.is_sqlite:
            proc_query = proc_query.with_for_update(skip_locked=True)

        p_job = proc_query.order_by(ProcessingJob.scheduled_at.asc()).first()
        if p_job:
            p_job.status = "running"
            p_job.started_at = now
            p_job.attempts += 1
            p_job.progress_percent = max(p_job.progress_percent or 0, 5)
            if not p_job.progress_stage or "Queued" in p_job.progress_stage:
                p_job.progress_stage = "Job started by worker..."
            self.db.commit()
            return p_job

        return None

    def mark_completed(self, job: Union[ScrapeJob, ProcessingJob]):
        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.progress_percent = 100
        if not job.progress_stage or "Fetching" in job.progress_stage or "Analyzing" in job.progress_stage:
            job.progress_stage = "Synchronization completed successfully."
        job.error_message = None
        self.db.commit()
        logger.info(f"Job {job.id} ({job.job_type}) marked as completed.")

    def mark_failed(self, job: Union[ScrapeJob, ProcessingJob], error: str, retry_delay_seconds: int = 60):
        now = datetime.now(timezone.utc)
        job.error_message = str(error)
        job.progress_stage = f"Failed: {error}"

        if job.attempts < job.max_attempts:
            job.status = "queued"
            # Exponential backoff: 60s, 120s, 240s...
            backoff = retry_delay_seconds * (2 ** (job.attempts - 1))
            job.scheduled_at = now + timedelta(seconds=backoff)
            logger.warning(f"Job {job.id} ({job.job_type}) failed: {error}. Rescheduled attempt {job.attempts + 1} for {job.scheduled_at}.")
        else:
            job.status = "failed"
            job.completed_at = now
            logger.error(f"Job {job.id} ({job.job_type}) permanently failed after {job.attempts} attempts: {error}")

        self.db.commit()

    def recover_stale_jobs(self, timeout_minutes: int = 15) -> int:
        """Finds any orphan jobs stuck in 'running' status (e.g. from an abrupt restart or crash) and resets them."""
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=timeout_minutes)
        threshold_cmp = threshold.replace(tzinfo=None) if settings.is_sqlite else threshold

        recovered = 0
        for model in (ScrapeJob, ProcessingJob):
            stale_jobs = self.db.query(model).filter(
                model.status == "running",
                or_(model.started_at <= threshold, model.started_at <= threshold_cmp),
            ).all()
            for job in stale_jobs:
                if job.attempts < job.max_attempts:
                    job.status = "queued"
                    job.progress_stage = "Job recovered from previous worker interruption; queued for retry."
                else:
                    job.status = "failed"
                    job.completed_at = now
                    job.error_message = "Job timed out and permanently failed after worker interruption."
                recovered += 1

        if recovered > 0:
            self.db.commit()
            logger.info(f"Recovered {recovered} stale/interrupted job(s) in queue.")
        return recovered
