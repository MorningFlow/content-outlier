from datetime import datetime, timezone, timedelta
from app.models.job import ScrapeJob
from app.worker.queue import JobQueue


def test_job_queue_acquire_and_retry(db_session):
    queue = JobQueue(db_session)
    now = datetime.now(timezone.utc)

    job = ScrapeJob(
        job_type="initial_profile_sync",
        status="queued",
        scheduled_at=now - timedelta(minutes=1),
        max_attempts=2,
    )
    db_session.add(job)
    db_session.commit()

    # Acquire job
    acquired = queue.acquire_next_job()
    assert acquired is not None
    assert acquired.id == job.id
    assert acquired.status == "running"
    assert acquired.attempts == 1

    # Simulate temporary failure -> should be rescheduled with backoff
    queue.mark_failed(acquired, error="Network timeout", retry_delay_seconds=30)
    assert acquired.status == "queued"
    assert acquired.attempts == 1

    # Ensure timezone safe comparison
    sched = acquired.scheduled_at
    if sched.tzinfo is None:
        sched = sched.replace(tzinfo=timezone.utc)
    assert sched > now

    # Fast forward time to simulate retry execution
    acquired.scheduled_at = now - timedelta(seconds=1)
    db_session.commit()

    re_acquired = queue.acquire_next_job()
    assert re_acquired.attempts == 2

    # Second failure reaches max_attempts -> permanently failed
    queue.mark_failed(re_acquired, error="Account deleted")
    assert re_acquired.status == "failed"
