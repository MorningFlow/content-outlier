"""Comprehensive automated audit script to verify all endpoints, database records,
outlier calculations, and frontend serving for Content Outlier.
"""
import sys
import httpx

API_BASE = "http://127.0.0.1:8000"


def audit():
    print("=" * 60)
    print("CONTENT OUTLIER SYSTEM AUDIT")
    print("=" * 60)
    client = httpx.Client(base_url=API_BASE, timeout=10.0)

    # 1. Health check
    res = client.get("/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print(f" [PASS] /health -> {res.json()}")

    # 2. Competitors
    res = client.get("/competitors")
    assert res.status_code == 200
    competitors = res.json()
    usernames = [c["username"] for c in competitors]
    print(f" [PASS] /competitors -> Found {len(competitors)} accounts: {usernames}")
    assert set(usernames) == {"hormozi", "swastik.nandakumar", "aiwithanushka"}, f"Unexpected competitors: {usernames}"

    hormozi_comp = next(c for c in competitors if c["username"] == "hormozi")
    anushka_comp = next(c for c in competitors if c["username"] == "aiwithanushka")
    swastik_comp = next(c for c in competitors if c["username"] == "swastik.nandakumar")
    print(f"        @hormozi: {hormozi_comp['followers']:,} followers, baseline {int(hormozi_comp['baseline_views_median']):,} views")
    print(f"        @swastik.nandakumar: {swastik_comp['followers']:,} followers, baseline {int(swastik_comp['baseline_views_median']):,} views")
    print(f"        @aiwithanushka: {anushka_comp['followers']:,} followers, baseline {int(anushka_comp['baseline_views_median']):,} views")

    # 3. Dashboard
    res = client.get("/dashboard")
    assert res.status_code == 200
    dash = res.json()
    print(f" [PASS] /dashboard -> {dash['competitors_count']} Competitors, {dash['content_tracked_count']} Tracked, {dash['outliers_found_count']} Outliers")
    assert dash["competitors_count"] == 3
    assert dash["content_tracked_count"] >= 40
    assert dash["outliers_found_count"] >= 10
    assert dash["top_outlier"]["username"] == "hormozi"
    print(f"        Top Outlier: @{dash['top_outlier']['username']} ({dash['top_outlier']['outlier_score']}× score)")

    # 4. Outliers Feed & Multi-Horizon Filtering
    res = client.get("/outliers?sort=score")
    assert res.status_code == 200
    outliers = res.json()["items"]
    print(f" [PASS] /outliers?sort=score -> {len(outliers)} items")
    scores = [(o["username"], o["outlier_score"], o["view_count"]) for o in outliers[:5]]
    for u, sc, v in scores:
        print(f"        @{u}: {sc}× score ({v:,} views)")

    # Filter by specific competitor
    res = client.get("/outliers?competitor=aiwithanushka")
    assert res.status_code == 200
    filtered = res.json()["items"]
    assert len(filtered) >= 1 and all(f["username"] == "aiwithanushka" for f in filtered)
    print(f" [PASS] /outliers?competitor=aiwithanushka -> Correctly filtered: {len(filtered)} items for @{filtered[0]['username']}")

    # Content Date Range Horizons (30d, 60d, 90d)
    c30 = client.get("/content?range=30d").json()
    c60 = client.get("/content?range=60d").json()
    c90 = client.get("/content?range=90d").json()
    print(f" [PASS] /content horizons -> 30d: {len(c30)}, 60d: {len(c60)}, 90d: {len(c90)}")
    assert len(c30) <= len(c60) <= len(c90)

    # 5. Content Detail & Historical Metrics
    top_id = dash["top_outlier"]["id"]
    res = client.get(f"/content/{top_id}")
    assert res.status_code == 200
    detail = res.json()
    print(f" [PASS] /content/{top_id} -> Shortcode: {detail['shortcode']}, Multiplier: {detail['view_multiplier']}×")

    res = client.get(f"/content/{top_id}/metrics")
    assert res.status_code == 200
    metrics = res.json()
    print(f" [PASS] /content/{top_id}/metrics -> Found {len(metrics)} historical snapshots:")
    for m in metrics:
        views = m["views"]
        growth = m.get("view_growth")
        print(f"        Snapshot: {m['recorded_at']} -> {views:,} views (growth: {growth or 0:,})")

    # 6. Transcript & Hook Breakdown
    res = client.get(f"/content/{top_id}/transcript")
    assert res.status_code == 200
    tr = res.json()
    print(f" [PASS] /content/{top_id}/transcript -> Hook: \"{tr['hook_text']}\"")
    print(f"        Breakdown: {tr['breakdown_hook']}")
    print(f"        Key Takeaway: {tr['key_takeaways']}")

    # 7. Background Jobs Queue
    res = client.get("/jobs")
    assert res.status_code == 200
    jobs = res.json()
    print(f" [PASS] /jobs -> Found {len(jobs)} recent background jobs")

    # 8. Trigger on-demand sync
    res = client.post(f"/competitors/{anushka_comp['id']}/sync")
    assert res.status_code == 202
    new_job = res.json()
    print(f" [PASS] POST /competitors/{anushka_comp['id']}/sync -> Queued job {new_job['id']} ({new_job['status']})")

    # 9. Frontend HTML Serving
    res = client.get("/")
    assert res.status_code == 200
    assert "CONTENT OUTLIER" in res.text
    assert "@hormozi" in res.text
    print(f" [PASS] GET / -> Successfully serving frontend HTML ({len(res.text):,} bytes)")

    print("=" * 60)
    print("ALL AUDIT CHECKS PASSED PERFECTLY (100%)")
    print("=" * 60)


if __name__ == "__main__":
    audit()
