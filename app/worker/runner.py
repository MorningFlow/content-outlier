import time
import logging
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from app.database import SessionLocal
from app.worker.queue import JobQueue
from app.worker.tasks import TaskExecutor
from app.worker.scheduler import start_scheduler
from app.models.job import ScrapeJob, ProcessingJob
from app.config import settings
from app.services.transcription_service import check_and_unload_whisper_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("worker")

_running = True


def _signal_handler(signum, frame):
    global _running
    logger.info("Shutdown signal received. Stopping worker loop...")
    _running = False


def process_single_job():
    """Fetches and executes a single job in a fresh DB session."""
    db = SessionLocal()
    queue = JobQueue(db)
    executor = TaskExecutor(db)

    job = None
    try:
        job = queue.acquire_next_job()
        if not job:
            return False

        logger.info(f"Picked up job {job.id} (type: {job.job_type})")

        if isinstance(job, ScrapeJob):
            executor.process_scrape_job(job)
        elif isinstance(job, ProcessingJob):
            executor.process_processing_job(job)

        queue.mark_completed(job)
        return True
    except Exception as e:
        logger.exception(f"Error executing job: {e}")
        if job:
            queue.mark_failed(job, error=str(e))
        return True
    finally:
        db.close()


def run_worker(poll_interval: float = settings.WORKER_POLL_INTERVAL):
    """Main worker loop executed on the VPS with adaptive backoff and idle resource cleanup."""
    global _running
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    logger.info("Starting Content Outlier VPS Background Worker...")
    try:
        init_db = SessionLocal()
        init_queue = JobQueue(init_db)
        init_queue.recover_stale_jobs()
        init_db.close()
    except Exception as e:
        logger.debug(f"Initial stale job cleanup error: {e}")

    scheduler = start_scheduler()

    current_poll = poll_interval
    max_poll = getattr(settings, "WORKER_MAX_POLL_INTERVAL", 30.0)

    try:
        while _running:
            had_work = process_single_job()
            if had_work:
                current_poll = 1.0  # Fast polling while queue has active work
            else:
                time.sleep(current_poll)
                current_poll = min(current_poll * 1.5, max_poll)
                # Free memory back to the OS if Whisper model is idle
                try:
                    check_and_unload_whisper_model()
                except Exception as e:
                    logger.debug(f"Error checking whisper model idle status: {e}")
    finally:
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        logger.info("Worker stopped successfully.")


if __name__ == "__main__":
    run_worker()
