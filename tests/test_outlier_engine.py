from datetime import datetime, timezone, timedelta
from app.services.outlier_engine import OutlierEngine
from app.models.content import Content
from app.models.competitor import Competitor


def test_competitor_baseline_median_calculation():
    engine = OutlierEngine()

    contents = [
        Content(view_count=10000, like_count=500, comment_count=50),
        Content(view_count=35000, like_count=1200, comment_count=100),
        Content(view_count=40000, like_count=1500, comment_count=150),
        Content(view_count=900000, like_count=45000, comment_count=2000),  # extreme viral spike
    ]

    base_views, base_eng = engine.compute_competitor_baseline(contents)
    # Median of [10000, 35000, 40000, 900000] is (35000 + 40000) / 2 = 37500.0
    assert base_views == 37500.0
    assert base_eng is not None
    assert base_eng > 0.0


def test_outlier_evaluation_multiplier_and_explainability():
    engine = OutlierEngine()

    competitor = Competitor(
        username="moveperformance",
        followers=100000,
        baseline_views_median=35000.0,
        baseline_engagement_rate=0.03,
    )

    now = datetime.now(timezone.utc)
    reel = Content(
        instagram_username="moveperformance",
        shortcode="TEST1234",
        published_at=now - timedelta(days=2),
        view_count=700000,  # 20x outlier
        like_count=35000,
        comment_count=1500,
    )

    eval_result = engine.evaluate_content(reel, competitor)

    assert eval_result["is_outlier"] is True
    assert eval_result["view_multiplier"] == 20.0
    assert eval_result["outlier_score"] >= 20.0
    assert eval_result["view_velocity"] is not None
    assert eval_result["outlier_reasons"]["view_multiplier"] == 20.0
    assert eval_result["outlier_reasons"]["account_baseline_views"] == 35000
    assert "20.0× more views" in eval_result["outlier_reasons"]["summary"]


def test_normal_performance_not_flagged_as_outlier():
    engine = OutlierEngine()

    competitor = Competitor(
        username="physiotips",
        followers=50000,
        baseline_views_median=20000.0,
        baseline_engagement_rate=0.035,
    )

    now = datetime.now(timezone.utc)
    reel = Content(
        instagram_username="physiotips",
        shortcode="NORM1234",
        published_at=now - timedelta(days=5),
        view_count=22000,  # 1.1x normal
        like_count=700,
        comment_count=40,
    )

    eval_result = engine.evaluate_content(reel, competitor)

    assert eval_result["is_outlier"] is False
    assert eval_result["view_multiplier"] == 1.1
    assert "within expected baseline" in eval_result["outlier_reasons"]["summary"]
