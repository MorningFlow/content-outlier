from datetime import datetime, timezone, timedelta
from app.models.competitor import Competitor
from app.models.content import Content
from app.models.metric import ContentMetric
from app.models.transcript import Transcript


def test_dashboard_and_outliers_flow(client, db_session):
    now = datetime.now(timezone.utc)

    # Setup competitor
    comp = Competitor(
        username="physioco",
        profile_name="Physio Co",
        followers=50000,
        baseline_views_median=25000.0,
        baseline_engagement_rate=0.03,
        last_scraped_at=now,
    )
    db_session.add(comp)
    db_session.flush()

    # Outlier post
    c1 = Content(
        competitor_id=comp.id,
        instagram_username="physioco",
        shortcode="REEL_OUTLIER",
        instagram_url="https://www.instagram.com/reel/REEL_OUTLIER/",
        published_at=now - timedelta(days=3),
        view_count=500000,
        like_count=25000,
        comment_count=1000,
        is_outlier=True,
        outlier_score=20.0,
        view_multiplier=20.0,
        outlier_reasons={"view_multiplier": 20.0, "summary": "Viral spike"},
    )
    db_session.add(c1)
    db_session.flush()

    # Add historical metric snapshot
    m1 = ContentMetric(
        content_id=c1.id,
        recorded_at=now - timedelta(days=1),
        views=300000,
        likes=15000,
        comments=600,
    )
    m2 = ContentMetric(
        content_id=c1.id,
        recorded_at=now,
        views=500000,
        likes=25000,
        comments=1000,
        view_growth=200000,
        view_velocity=8333.3,
    )
    db_session.add_all([m1, m2])

    # Add transcript
    tr = Transcript(
        content_id=c1.id,
        full_text="Test transcript text.",
        segments=[{"start": 0.0, "end": 4.0, "text": "Test transcript text."}],
        hook_text="Test transcript hook",
        breakdown_hook="Hook breakdown details",
    )
    db_session.add(tr)
    db_session.commit()

    # 1. Test /dashboard
    dash_res = client.get("/dashboard")
    assert dash_res.status_code == 200
    dash_data = dash_res.json()
    assert dash_data["competitors_count"] == 1
    assert dash_data["content_tracked_count"] == 1
    assert dash_data["outliers_found_count"] == 1
    assert dash_data["top_outlier"]["shortcode"] == "REEL_OUTLIER"

    # 2. Test /outliers
    outliers_res = client.get("/outliers?sort=score&min_score=3.0")
    assert outliers_res.status_code == 200
    outliers_data = outliers_res.json()
    assert outliers_data["total"] == 1
    assert outliers_data["items"][0]["shortcode"] == "REEL_OUTLIER"

    # 3. Test /content/{id}
    detail_res = client.get(f"/content/{c1.id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["shortcode"] == "REEL_OUTLIER"
    assert len(detail["metrics"]) == 2
    assert detail["transcript"]["hook_text"] == "Test transcript hook"

    # 4. Test /content/{id}/metrics
    metrics_res = client.get(f"/content/{c1.id}/metrics")
    assert metrics_res.status_code == 200
    assert len(metrics_res.json()) == 2

    # 5. Test /content/{id}/transcript
    tr_res = client.get(f"/content/{c1.id}/transcript")
    assert tr_res.status_code == 200
    assert tr_res.json()["breakdown_hook"] == "Hook breakdown details"
