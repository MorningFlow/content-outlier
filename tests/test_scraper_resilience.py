import time
import pytest
from unittest.mock import MagicMock
from app.scraper.collector import InstagramCollector
from app.scraper.exceptions import RateLimitException, ProfileNotFoundException


def test_null_metric_preservation_not_zero():
    """Requirement 3: Treat unavailable metrics as 'NULL', NOT zero. Do not fabricate or estimate unavailable Instagram metrics."""
    collector = InstagramCollector()

    # Mock Post object where views, shares, saves are unavailable/hidden by Instagram
    mock_post = MagicMock()
    mock_post.mediaid = 987654321
    mock_post.shortcode = "NULL_METRIC_REEL"
    mock_post.is_video = True
    mock_post.typename = "GraphVideo"
    mock_post.video_url = "https://instagram.com/reel/NULL_METRIC_REEL.mp4"
    mock_post.url = "https://instagram.com/reel/NULL_METRIC_REEL.jpg"
    mock_post.video_view_count = None  # Views hidden or unavailable
    mock_post.likes = None            # Likes hidden by user
    mock_post.comments = 14
    mock_post.video_duration = 15.0
    mock_post.caption = "Testing null safety"
    mock_post.caption_hashtags = ["test"]
    mock_post.caption_mentions = []
    mock_post.date_utc = None
    mock_post._node = {}              # No internal play_count or share_count

    extracted = collector._extract_post_metadata(mock_post, "testuser", "12345")

    # Verify NULL is preserved, NOT converted to 0
    assert extracted["view_count"] is None
    assert extracted["like_count"] is None
    assert extracted["share_count"] is None
    assert extracted["save_count"] is None
    assert extracted["comment_count"] == 14


def test_rate_limit_exception_handling():
    collector = InstagramCollector()
    mock_client = collector.client

    # Simulate 429 Too Many Requests
    err = Exception("429 Too Many Requests: query rate limit exceeded")
    with pytest.raises(RateLimitException) as exc_info:
        mock_client.handle_instaloader_exception(err, "ratelimited_user")

    assert exc_info.value.retry_after_seconds > 0


def test_unauthenticated_clips_extraction():
    collector = InstagramCollector()
    mock_media = {
        "code": "C999XYZ",
        "pk": 11223344,
        "play_count": 88000,
        "like_count": 4200,
        "comment_count": 120,
        "caption": {"text": "Exciting reel #growth @partner"},
        "video_versions": [{"url": "https://cdn.instagram.com/v.mp4"}],
        "image_versions2": {"candidates": [{"url": "https://cdn.instagram.com/t.jpg"}]},
        "video_duration": 22.5,
        "taken_at": int(time.time()) - 3600,
    }
    mock_resp = {
        "data": {
            "xdt_api__v1__clips__user__connection_v2": {
                "edges": [{"node": {"media": mock_media}}],
                "page_info": {"has_next_page": False, "end_cursor": None},
            }
        }
    }
    collector.loader.context.doc_id_graphql_query = MagicMock(return_value=mock_resp)
    collector._shortcode_cache["testuser"] = []
    collector._user_id_cache["testuser"] = "998877"

    items = collector._fetch_reels_unauthenticated("testuser", max_items=5)
    assert len(items) == 1
    item = items[0]
    assert item["shortcode"] == "C999XYZ"
    assert item["view_count"] == 88000
    assert item["like_count"] == 4200
    assert item["comment_count"] == 120
    assert item["video_url"] == "https://cdn.instagram.com/v.mp4"
    assert "growth" in item["hashtags"]
    assert "partner" in item["mentions"]

