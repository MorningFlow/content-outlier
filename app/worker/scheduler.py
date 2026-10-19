import logging
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal
from app.models.competitor import Competitor
from app.models.job import ScrapeJob
from app.config import settings

logger = logging.getLogger(__name__)


def schedule_incremental_scrapes():
    """Periodic job that queues incremental scrape jobs for all active competitors."""
    db = SessionLocal()
    try:
        active_comps = db.query(Competitor).filter(Competitor.status == "active").all()
        now = datetime.now(timezone.utc)
        count = 0
        for comp in active_comps:
            # Avoid queuing duplicate active scrape jobs
            existing_job = db.query(ScrapeJob).filter(
                ScrapeJob.competitor_id == comp.id,
                ScrapeJob.status.in_(["queued", "running"]),
            ).first()

            if not existing_job:
                job = ScrapeJob(
                    job_type="incremental_profile_sync",
                    status="queued",
                    competitor_id=comp.id,
                    scheduled_at=now,
                    payload={"username": comp.username},
                )
                db.add(job)
                count += 1

        db.commit()
        if count > 0:
            logger.info(f"Scheduled incremental scrapes for {count} active competitor accounts.")
    except Exception as e:
        logger.error(f"Error scheduling incremental scrapes: {e}")
        db.rollback()
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    """Initializes and starts the periodic background scheduler.

    When ON_DEMAND_ONLY is True the scheduler starts (so the worker loop can
    still process manually-triggered jobs) but no automatic scrape jobs are
    queued — scraping only happens when triggered via the API on platform open.
    """
    scheduler = BackgroundScheduler()

    if settings.ON_DEMAND_ONLY:
        logger.info("ON_DEMAND_ONLY=True: automatic scheduled scrapes are disabled. Scraping on platform open only.")
    else:
        scheduler.add_job(
            schedule_incremental_scrapes,
            "interval",
            hours=settings.DEFAULT_SCAN_INTERVAL_HOURS,
            id="incremental_scrapes_job",
            replace_existing=True,
        )
        logger.info(f"Started scheduler running every {settings.DEFAULT_SCAN_INTERVAL_HOURS} hours.")

    scheduler.start()
    return scheduler
