import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from app.models.competitor import Competitor
from app.models.content import Content
from app.models.metric import ContentMetric
from app.services.content_service import ContentService
from app.services.transcription_service import TranscriptionService, check_and_unload_whisper_model, get_whisper_model
import app.services.transcription_service as ts_mod


def _make_competitor(db, username="res_test_creator"):
    comp = Competitor(
        username=username,
        profile_name="Resource Test Creator",
        followers=5000,
        baseline_views_median=1000.0,
        baseline_engagement_rate=0.03,
        last_scraped_at=datetime.now(timezone.utc),
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


def test_delta_gated_metric_snapshots(db_session):
    """Test that static post metrics do not produce redundant ContentMetric database rows."""
    comp = _make_competitor(db_session, "deltacreator")
    service = ContentService(db_session)

    items = [
        {
            "instagram_username": "deltacreator",
            "instagram_url": "https://www.instagram.com/reel/SC101/",
            "post_id": "P101",
            "shortcode": "SC101",
            "content_type": "reel",
            "published_at": datetime.now(timezone.utc),
            "view_count": 10000,
            "like_count": 500,
            "comment_count": 50,
            "share_count": 10,
            "save_count": 20,
        }
    ]

    # First ingest should record initial ContentMetric snapshot
    service.ingest_scraped_items(comp.id, items)
    content = db_session.query(Content).filter(Content.shortcode == "SC101").first()
    assert content is not None

    snapshots_1 = db_session.query(ContentMetric).filter(ContentMetric.content_id == content.id).count()
    assert snapshots_1 == 1

    # Second ingest with IDENTICAL metrics should be delta-gated (0 new rows)
    service.ingest_scraped_items(comp.id, items)
    snapshots_2 = db_session.query(ContentMetric).filter(ContentMetric.content_id == content.id).count()
    assert snapshots_2 == 1, "Duplicate snapshot was inserted despite identical metrics"

    # Third ingest with CHANGED view count should create a new snapshot
    items_changed = [
        {
            "instagram_username": "deltacreator",
            "instagram_url": "https://www.instagram.com/reel/SC101/",
            "post_id": "P101",
            "shortcode": "SC101",
            "content_type": "reel",
            "published_at": datetime.now(timezone.utc),
            "view_count": 15000,  # 50% increase
            "like_count": 500,
            "comment_count": 50,
            "share_count": 10,
            "save_count": 20,
        }
    ]
    service.ingest_scraped_items(comp.id, items_changed)
    snapshots_3 = db_session.query(ContentMetric).filter(ContentMetric.content_id == content.id).count()
    assert snapshots_3 == 2, "Expected a new snapshot when view count grew significantly"


def test_ephemeral_transcription_media_cleanup(db_session, tmp_path):
    """Test that temporary media files created during transcription are deleted upon completion."""
    comp = _make_competitor(db_session, "cleanupcreator")
    content = Content(
        competitor_id=comp.id,
        instagram_username="cleanupcreator",
        shortcode="TEMP_CLEANUP_01",
        instagram_url="https://www.instagram.com/reel/TEMP_CLEANUP_01/",
        caption="Sample caption for cleanup test",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(content)
    db_session.commit()

    service = TranscriptionService(db_session)
    temp_media = tmp_path / "temp_reel.mp4"
    temp_media.write_bytes(b"ephemeral media data")
    service._temp_files.add(str(temp_media))

    with patch.object(service, "_ensure_video_file", return_value=temp_media):
        with patch.object(service, "_transcribe_audio_file", return_value={
            "full_text": "Transcribed voice content",
            "language": "en",
            "duration": 10.0,
            "segments": [],
        }):
            tr = service.transcribe_content(content.id)
            assert tr is not None
            assert tr.full_text == "Transcribed voice content"

    # The temporary media file MUST have been deleted
    assert not temp_media.exists(), "Ephemeral media file was not cleaned up after transcription"
    assert str(temp_media) not in service._temp_files


def test_whisper_model_idle_unloading():
    """Test that check_and_unload_whisper_model releases the model after idle timeout."""
    mock_model = MagicMock()
    ts_mod._whisper_model = mock_model
    # Set last used to 100 seconds ago
    ts_mod._whisper_last_used = time.time() - 100

    # With 200s TTL, it should NOT unload
    unloaded = check_and_unload_whisper_model(max_idle_seconds=200)
    assert not unloaded
    assert ts_mod._whisper_model is not None

    # With 50s TTL, it SHOULD unload
    unloaded = check_and_unload_whisper_model(max_idle_seconds=50)
    assert unloaded
    assert ts_mod._whisper_model is None
