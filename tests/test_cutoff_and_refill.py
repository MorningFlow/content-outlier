import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from app.scraper.collector import InstagramCollector
from app.models.competitor import Competitor
from app.models.content import Content
from app.models.job import ScrapeJob
from app.worker.tasks import TaskExecutor


def test_30_day_cutoff_stops_pagination():
    """Verify that clips older than the days cutoff (default 30) are not collected and stop pagination."""
    collector = InstagramCollector()
    now_ts = int(datetime.now(timezone.utc).timestamp())
    day_sec = 86400

    # Mock doc_id_graphql_query to return 3 edges:
    # 1. 5 days ago (should collect)
    # 2. 15 days ago (should collect)
    # 3. 35 days ago (should trigger 30-day cutoff and halt)
    # 4. 40 days ago (should never be collected)
    mock_edges = [
        {"node": {"media": {"code": "POST_5D", "pk": 1001, "taken_at": now_ts - (5 * day_sec), "play_count": 5000}}},
        {"node": {"media": {"code": "POST_15D", "pk": 1002, "taken_at": now_ts - (15 * day_sec), "play_count": 15000}}},
        {"node": {"media": {"code": "POST_35D", "pk": 1003, "taken_at": now_ts - (35 * day_sec), "play_count": 35000}}},
        {"node": {"media": {"code": "POST_40D", "pk": 1004, "taken_at": now_ts - (40 * day_sec), "play_count": 40000}}},
    ]

    mock_resp = {
        "data": {
            "xdt_api__v1__clips__user__connection_v2": {
                "edges": mock_edges,
                "page_info": {"has_next_page": True, "end_cursor": "cursor_2"},
            }
        }
    }

    with patch.object(collector.loader.context, "doc_id_graphql_query", return_value=mock_resp):
        collector._user_id_cache["testcreator"] = "998877"
        items = collector.fetch_reels_and_videos("testcreator", max_items=50, days_cutoff=30)

        codes = [item["shortcode"] for item in items]
        assert "POST_5D" in codes
        assert "POST_15D" in codes
        assert "POST_35D" not in codes
        assert "POST_40D" not in codes
        assert len(items) == 2


def test_refill_boundary_skips_existing_database_posts_and_halts():
    """Verify that when refilling an account with existing database shortcodes,
    existing items are not collected and pagination terminates immediately without retry.
    """
    collector = InstagramCollector()
    now_ts = int(datetime.now(timezone.utc).timestamp())
    day_sec = 86400

    # Mock edges:
    # 1. New Reel posted 1 day ago (not in DB -> collect)
    # 2. Existing Reel posted 3 days ago (in DB -> boundary reached -> halt pagination)
    # 3. Existing Reel posted 4 days ago (in DB -> skip)
    mock_edges = [
        {"node": {"media": {"code": "NEW_REEL_1", "pk": 2001, "taken_at": now_ts - (1 * day_sec), "play_count": 1000}}},
        {"node": {"media": {"code": "OLD_REEL_IN_DB", "pk": 2002, "taken_at": now_ts - (3 * day_sec), "play_count": 8000}}},
        {"node": {"media": {"code": "OLDER_REEL_IN_DB", "pk": 2003, "taken_at": now_ts - (4 * day_sec), "play_count": 12000}}},
    ]

    mock_resp = {
        "data": {
            "xdt_api__v1__clips__user__connection_v2": {
                "edges": mock_edges,
                "page_info": {"has_next_page": True, "end_cursor": "cursor_next_page"},
            }
        }
    }

    existing_shortcodes = {"OLD_REEL_IN_DB", "OLDER_REEL_IN_DB"}

    with patch.object(collector.loader.context, "doc_id_graphql_query", return_value=mock_resp) as mock_query:
        collector._user_id_cache["existing_user"] = "112233"
        # Seed shortcode cache with old DB shortcodes to test Step D immunity
        collector._shortcode_cache["existing_user"] = ["OLD_REEL_IN_DB"]

        items = collector.fetch_reels_and_videos(
            "existing_user",
            max_items=50,
            days_cutoff=30,
            existing_shortcodes=existing_shortcodes,
        )

        codes = [item["shortcode"] for item in items]
        # Only the brand new reel should be collected
        assert codes == ["NEW_REEL_1"]
        # Only 1 GraphQL page should have been queried because boundary_hit halted pagination
        assert mock_query.call_count == 1


def test_refill_up_to_date_when_no_new_posts(db_session):
    """Verify that when refilling an account where no new posts exist,
    the task marks it completed and up-to-date rather than failing with needs_auth.
    """
    comp = Competitor(
        username="uptodate_user",
        instagram_id="554433",
        status="active",
        followers=10000,
    )
    db_session.add(comp)
    db_session.flush()

    content = Content(
        competitor_id=comp.id,
        instagram_username="uptodate_user",
        shortcode="EXISTING_SC_1",
        instagram_url="https://instagram.com/reel/EXISTING_SC_1/",
        published_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db_session.add(content)
    db_session.commit()

    job = ScrapeJob(
        job_type="incremental_profile_sync",
        competitor_id=comp.id,
        status="queued",
        payload={"username": "uptodate_user"},
    )
    db_session.add(job)
    db_session.commit()

    mock_collector = MagicMock()
    mock_collector.resolve_profile.return_value = {
        "username": "uptodate_user",
        "instagram_id": "554433",
        "followers": 10000,
    }
    # No new posts found during refill
    mock_collector.fetch_reels_and_videos.return_value = []
    mock_collector.loader.context.is_logged_in = False

    executor = TaskExecutor(db_session, collector=mock_collector)
    executor.process_scrape_job(job)

    db_session.refresh(comp)
    assert comp.status == "active"
    assert comp.scrape_error is None
    assert "up to date" in (job.progress_stage or "").lower()


def test_incremental_sync_stops_at_since_timestamp():
    """Verify that incremental sync after the first run only fetches content
    published strictly AFTER the newest post in the database.
    """
    collector = InstagramCollector()
    now = datetime.now(timezone.utc)
    day = timedelta(days=1)

    # Database latest post was published 3 days ago
    since_ts = now - (3 * day)
    since_ts_int = int(since_ts.timestamp())

    # Edges from Instagram:
    # 1. 1 day ago (NEW -> collect)
    # 2. 2 days ago (NEW -> collect)
    # 3. 3 days ago (Matches latest DB post -> boundary hit -> halt!)
    # 4. 4 days ago (Older -> should never be queried or collected)
    mock_edges = [
        {"node": {"media": {"code": "POST_1D_AGO", "pk": 3001, "taken_at": int((now - day).timestamp()), "play_count": 1200}}},
        {"node": {"media": {"code": "POST_2D_AGO", "pk": 3002, "taken_at": int((now - 2 * day).timestamp()), "play_count": 3400}}},
        {"node": {"media": {"code": "POST_3D_LATEST_DB", "pk": 3003, "taken_at": since_ts_int, "play_count": 5600}}},
        {"node": {"media": {"code": "POST_4D_OLD", "pk": 3004, "taken_at": int((now - 4 * day).timestamp()), "play_count": 7800}}},
    ]

    mock_resp = {
        "data": {
            "xdt_api__v1__clips__user__connection_v2": {
                "edges": mock_edges,
                "page_info": {"has_next_page": True, "end_cursor": "cursor_next"},
            }
        }
    }

    with patch.object(collector.loader.context, "doc_id_graphql_query", return_value=mock_resp) as mock_query:
        collector._user_id_cache["creator_3d"] = "776655"
        items = collector.fetch_reels_and_videos(
            "creator_3d",
            max_items=12,
            since_timestamp=since_ts,
            latest_shortcode="POST_3D_LATEST_DB",
            existing_shortcodes={"POST_3D_LATEST_DB", "POST_4D_OLD"},
        )

        codes = [item["shortcode"] for item in items]
        # Only the posts published strictly after 3 days ago should be returned
        assert codes == ["POST_1D_AGO", "POST_2D_AGO"]
        assert "POST_3D_LATEST_DB" not in codes
        assert "POST_4D_OLD" not in codes
        assert mock_query.call_count == 1


def test_stale_job_recovery(db_session):
    """Verify that orphan jobs stuck in 'running' status are recovered on startup."""
    from app.worker.queue import JobQueue

    queue = JobQueue(db_session)
    old_time = datetime.now(timezone.utc) - timedelta(minutes=30)

    comp = Competitor(username="stale_comp", instagram_id="1234")
    db_session.add(comp)
    db_session.flush()

    stale_job = ScrapeJob(
        job_type="incremental_profile_sync",
        competitor_id=comp.id,
        status="running",
        started_at=old_time,
        attempts=1,
        max_attempts=3,
    )
    db_session.add(stale_job)
    db_session.commit()

    recovered = queue.recover_stale_jobs(timeout_minutes=15)
    assert recovered == 1

    db_session.refresh(stale_job)
    assert stale_job.status == "queued"
    assert "recovered" in stale_job.progress_stage.lower()


def test_sync_all_active_job_safety(db_session):
    """Verify that /competitors/sync-all does not crash when active jobs exist on CompetitorResponse."""
    from app.api.competitors import trigger_all_competitors_sync
    from app.models.competitor import Competitor
    from app.models.job import ScrapeJob

    comp = Competitor(username="active_job_comp", status="active")
    db_session.add(comp)
    db_session.flush()

    active_job = ScrapeJob(
        job_type="incremental_profile_sync",
        competitor_id=comp.id,
        status="running",
        attempts=1,
    )
    db_session.add(active_job)
    db_session.commit()

    # Calling trigger_all_competitors_sync should safely skip without throwing AttributeError on JobResponse
    result = trigger_all_competitors_sync(db=db_session)
    assert "active_job_comp" in result["skipped"]
    assert "active_job_comp" not in result["queued"]
