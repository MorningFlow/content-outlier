from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app.models.competitor import Competitor
from app.models.content import Content
from app.models.transcript import Transcript
from app.services.transcription_service import TranscriptionService


def _create_competitor(db_session, username="testcreator"):
    comp = Competitor(
        username=username,
        profile_name="Test Creator",
        followers=10000,
        baseline_views_median=5000.0,
        baseline_engagement_rate=0.04,
        last_scraped_at=datetime.now(timezone.utc),
    )
    db_session.add(comp)
    db_session.flush()
    return comp


def test_transcription_service_caption_only(db_session):
    comp = _create_competitor(db_session, "fallbackcreator")
    content = Content(
        competitor_id=comp.id,
        instagram_username="fallbackcreator",
        shortcode="TESTSC123",
        instagram_url="https://www.instagram.com/reel/TESTSC123/",
        caption="First hook line of test reel.\nFollow this advice to scale fast.",
        video_duration=15.0,
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(content)
    db_session.commit()

    service = TranscriptionService(db_session)
    tr = service.transcribe_content(content.id)

    assert tr is not None
    assert tr.content_id == content.id
    assert "First hook line of test reel" in tr.full_text
    assert len(tr.segments) == 0
    assert tr.hook_text == "First hook line of test reel."
    assert content.transcription_status == "completed"


def test_transcription_service_non_vocal(db_session, tmp_path):
    comp = _create_competitor(db_session, "silentcreator")
    video_file = tmp_path / "silent.mp4"
    video_file.write_bytes(b"silent video data")

    content = Content(
        competitor_id=comp.id,
        instagram_username="silentcreator",
        shortcode="SILENT123",
        instagram_url="https://www.instagram.com/reel/SILENT123/",
        video_path=str(video_file),
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(content)
    db_session.commit()

    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.duration = 7.0

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], mock_info)

    service = TranscriptionService(db_session)
    with patch("app.services.transcription_service.get_whisper_model", return_value=mock_model):
        with patch.object(service, "_ensure_video_file", return_value=video_file):
            tr = service.transcribe_content(content.id)

    assert tr is not None
    assert "No spoken dialogue detected" in tr.full_text
    assert len(tr.segments) == 0


def test_transcription_service_whisper_mock(db_session, tmp_path):
    comp = _create_competitor(db_session, "whispercreator")
    video_file = tmp_path / "test.mp4"
    video_file.write_bytes(b"dummy mp4 data")

    content = Content(
        competitor_id=comp.id,
        instagram_username="whispercreator",
        shortcode="REALVIDEO123",
        instagram_url="https://www.instagram.com/reel/REALVIDEO123/",
        video_path=str(video_file),
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(content)
    db_session.commit()

    mock_segment = MagicMock()
    mock_segment.start = 0.0
    mock_segment.end = 4.2
    mock_segment.text = "This is a real spoken audio sentence."

    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.duration = 4.2

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    service = TranscriptionService(db_session)
    with patch("app.services.transcription_service.get_whisper_model", return_value=mock_model):
        with patch.object(service, "_ensure_video_file", return_value=video_file):
            tr = service.transcribe_content(content.id)

    assert tr is not None
    assert tr.full_text == "This is a real spoken audio sentence."
    assert len(tr.segments) == 1
    assert tr.segments[0]["start"] == 0.0
    assert tr.segments[0]["end"] == 4.2
    assert tr.segments[0]["text"] == "This is a real spoken audio sentence."
    assert tr.language == "en"
    assert tr.duration == 4.2
    assert content.transcription_status == "completed"


def test_api_transcribe_endpoint(client, db_session):
    comp = _create_competitor(db_session, "endpointcreator")
    content = Content(
        competitor_id=comp.id,
        instagram_username="endpointcreator",
        shortcode="ENDPTSHORT1",
        instagram_url="https://www.instagram.com/reel/ENDPTSHORT1/",
        caption="Direct line 1\nDirect line 2",
        video_duration=22.0,
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(content)
    db_session.commit()

    res = client.post(f"/content/{content.id}/transcribe")
    assert res.status_code == 200
    data = res.json()
    assert data["content_id"] == content.id
    assert "Direct line 1" in data["full_text"]


def test_on_demand_mode_queues_zero_transcription_jobs(db_session):
    from app.services.content_service import ContentService
    from app.models.job import ProcessingJob
    from app.config import settings

    comp = _create_competitor(db_session, "on_demand_creator")
    service = ContentService(db_session)

    # Ingest 3 items that trigger outlier status
    items = [
        {
            "shortcode": f"OUTLIER_{i}",
            "instagram_username": "on_demand_creator",
            "instagram_url": f"https://www.instagram.com/reel/OUTLIER_{i}/",
            "published_at": datetime.now(timezone.utc),
            "caption": f"Reel #{i}",
            "view_count": 50000 * (i + 1),
            "like_count": 2000,
            "comment_count": 100,
        }
        for i in range(3)
    ]

    with patch.object(settings, "TRANSCRIPTION_MODE", "on_demand"):
        with patch.object(settings, "AUTO_TRANSCRIBE_OUTLIERS", False):
            saved = service.ingest_scraped_items(comp.id, items)

    # Confirm items ingested as outliers
    assert len(saved) == 3
    # Check that NO transcription processing jobs were added
    transcription_jobs = db_session.query(ProcessingJob).filter(ProcessingJob.job_type == "transcription").all()
    assert len(transcription_jobs) == 0


def test_transcription_service_passes_vad_and_beam_size(db_session, tmp_path):
    comp = _create_competitor(db_session, "vadcreator")
    video_file = tmp_path / "vad_test.mp4"
    video_file.write_bytes(b"dummy data")

    content = Content(
        competitor_id=comp.id,
        instagram_username="vadcreator",
        shortcode="VAD123",
        instagram_url="https://www.instagram.com/reel/VAD123/",
        video_path=str(video_file),
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(content)
    db_session.commit()

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], MagicMock(language="en", duration=5.0))

    service = TranscriptionService(db_session)
    with patch("app.services.transcription_service.get_whisper_model", return_value=mock_model):
        with patch.object(service, "_ensure_video_file", return_value=video_file):
            service.transcribe_content(content.id)

    mock_model.transcribe.assert_called_once()
    _, kwargs = mock_model.transcribe.call_args
    assert kwargs.get("beam_size") == 1
    assert kwargs.get("vad_filter") is True
    assert kwargs.get("temperature") == 0.0

