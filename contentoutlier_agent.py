"""
ContentOutlier Local Scraping Agent
====================================
Runs on your local machine (residential IP) and scrapes Instagram on behalf
of the VPS, which can't do it directly due to datacenter IP blocks.

HOW IT WORKS
------------
1. This script starts a local background server on http://localhost:9191
2. When you open contentoutlier.mytaskengine.com in your browser, the
   platform detects this agent and triggers a scrape
3. The agent retrieves scraping credentials from the platform API dynamically
4. The agent scrapes Instagram directly from your residential IP
5. If an Instagram session expires, the agent automatically re-authenticates
   and renews the session on the fly
6. Results are pushed to your VPS API for storage and outlier analysis
"""

import os
import sys
import re
import json
import time
import logging
import threading
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple

# ── Configuration ─────────────────────────────────────────────────────────────

VPS_API_URL = os.environ.get("CONTENTOUTLIER_API_URL", "https://contentoutlier.mytaskengine.com/api")
AGENT_PORT = int(os.environ.get("CONTENTOUTLIER_AGENT_PORT", "9191"))
MAX_REELS = int(os.environ.get("CONTENTOUTLIER_MAX_REELS", "50"))
SCRAPE_DELAY = float(os.environ.get("CONTENTOUTLIER_SCRAPE_DELAY", "2.0"))

# Local session storage directory
SESSION_DIR = Path(__file__).resolve().parent / ".agent_sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("contentoutlier-agent")

# ── Dependency check ──────────────────────────────────────────────────────────

def check_deps():
    missing = []
    for pkg in ["instaloader", "requests", "flask", "flask_cors"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg.replace("_", "-"))
    if missing:
        logger.error(f"Missing packages: {', '.join(missing)}")
        logger.error(f"Install with: pip install {' '.join(missing)}")
        sys.exit(1)

check_deps()

import instaloader
import requests
from flask import Flask, jsonify, request as flask_request
from flask_cors import CORS

# ── Credentials & Dynamic Session Management ──────────────────────────────────

_current_creds = {"username": None, "password": None}


def fetch_credentials_from_vps() -> Tuple[Optional[str], Optional[str]]:
    """Fetches dynamic Instagram scraping credentials stored in the platform settings."""
    url = f"{VPS_API_URL.rstrip('/')}/settings/instagram/credentials"
    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            data = r.json()
            u = data.get("username")
            p = data.get("password")
            if u:
                _current_creds["username"] = u
            if p:
                _current_creds["password"] = p
            return u, p
    except Exception as e:
        logger.debug(f"Could not fetch credentials from VPS: {e}")
    return _current_creds.get("username"), _current_creds.get("password")


def build_loader() -> instaloader.Instaloader:
    """Builds an Instaloader instance with session auto-loaded and rate-limits unfrozen."""
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        request_timeout=20.0,
        max_connection_attempts=1,
    )

    # Disable Instaloader 666-second freeze on rate limits
    if hasattr(loader.context, "_rate_controller"):
        loader.context._rate_controller.handle_429 = lambda query_type: None
        loader.context._rate_controller.sleep = lambda secs: None

    username, password = fetch_credentials_from_vps()

    if username:
        clean = username.strip().lstrip("@").lower()
        session_file = SESSION_DIR / f"{clean}.session"

        # 1. Try loading persistent local session file
        if session_file.is_file():
            try:
                loader.load_session_from_file(clean, str(session_file))
                logger.info(f"Loaded existing session file for @{clean}")
                return loader
            except Exception as e:
                logger.warning(f"Session file invalid or expired for @{clean} ({e})")

        # 2. Authenticate fresh if password exists
        if password:
            try:
                logger.info(f"Authenticating @{clean} on residential IP...")
                loader.login(clean, password)
                loader.save_session_to_file(str(session_file))
                logger.info(f"Saved fresh session file for @{clean}")
            except Exception as e:
                logger.warning(f"Login failed for @{clean}: {e}")

    return loader


def renew_agent_session(loader: instaloader.Instaloader) -> bool:
    """Auto-renews an expired session using stored platform credentials."""
    username, password = fetch_credentials_from_vps()
    if not username or not password:
        logger.warning("No credentials available for automatic session renewal.")
        return False

    clean = username.strip().lstrip("@").lower()
    session_file = SESSION_DIR / f"{clean}.session"
    logger.info(f"🔄 Auto-renewing Instagram session for @{clean}...")

    try:
        loader.login(clean, password)
        loader.save_session_to_file(str(session_file))
        logger.info(f"✓ Session successfully renewed and saved for @{clean}!")
        return True
    except Exception as e:
        logger.error(f"✗ Automatic session renewal failed: {e}")
        return False


# ── Scraper ───────────────────────────────────────────────────────────────────

def scrape_competitor(loader: instaloader.Instaloader, comp: dict, max_items: int = 50) -> dict:
    """Scrapes a competitor's Instagram profile and recent Reels/videos."""
    username = comp.get("username", "")
    clean = username.strip().lstrip("@").lower()
    logger.info(f"Scraping @{clean}...")

    profile_info = {
        "instagram_id": comp.get("instagram_id"),
        "profile_name": comp.get("profile_name") or clean,
        "profile_image": comp.get("profile_image"),
        "followers": comp.get("followers"),
    }
    posts = []
    seen = set()

    session = getattr(loader.context, "_session", None)
    is_auth = session and getattr(loader.context, "is_logged_in", False)

    # 1. Resolve profile id if missing
    profile_id = profile_info.get("instagram_id")
    if not profile_id and is_auth:
        profile_info = _resolve_via_search(session, clean) or profile_info
        profile_id = profile_info.get("instagram_id")

    # 2. Fetch Reels via clips GraphQL
    if profile_id:
        posts = _fetch_clips(loader, clean, profile_id, max_items, seen)

    logger.info(f"  → {len(posts)} posts collected for @{clean}")
    return {"profile": profile_info, "posts": posts}


def _resolve_via_search(session, username: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "x-ig-app-id": "936619743392459",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def _search(query):
        try:
            r = session.get(
                f"https://www.instagram.com/web/search/topsearch/?context=blended&query={query}",
                headers=headers,
                timeout=12,
            )
            if r.status_code == 200:
                for u in r.json().get("users", []):
                    ui = u.get("user", {})
                    if (ui.get("username") or "").lower() == username.lower():
                        return ui
        except Exception as e:
            logger.debug(f"Search '{query}' failed: {e}")
        return None

    for query in [username, username.split(".")[0]]:
        ui = _search(query)
        if ui:
            return {
                "instagram_id": str(ui.get("pk", "")),
                "profile_name": ui.get("full_name") or username,
                "profile_image": ui.get("profile_pic_url"),
                "followers": None,
                "is_private": ui.get("is_private", False),
            }
    return {}


def _fetch_clips(
    loader: instaloader.Instaloader,
    username: str,
    profile_id: str,
    max_items: int,
    seen: set,
) -> list:
    """Paginates the Instagram clips GraphQL endpoint with auto-renewal on expiration."""
    collected = []
    cursor = None
    prev_cursor = None
    session = getattr(loader.context, "_session", None)
    is_auth = session and getattr(loader.context, "is_logged_in", False)

    graphql_url = "https://www.instagram.com/graphql/query"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "x-ig-app-id": "936619743392459",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://www.instagram.com/",
    }

    while len(collected) < max_items:
        variables = {
            "data": {
                "include_feed_video": True,
                "page_size": 12,
                "target_user_id": profile_id,
            }
        }
        if cursor:
            variables["data"]["max_id"] = cursor
            variables["data"]["after"] = cursor

        try:
            if is_auth:
                raw = session.post(
                    graphql_url,
                    data={"doc_id": "27234427476213202", "variables": json.dumps(variables)},
                    headers=headers,
                    timeout=15,
                )
                if raw.status_code == 401 or "require_login" in raw.text:
                    logger.info("Session expired during clips fetching; attempting auto-renewal...")
                    if renew_agent_session(loader):
                        session = getattr(loader.context, "_session", None)
                        raw = session.post(
                            graphql_url,
                            data={"doc_id": "27234427476213202", "variables": json.dumps(variables)},
                            headers=headers,
                            timeout=15,
                        )
                raw.raise_for_status()
                resp = raw.json()
            else:
                resp = loader.context.doc_id_graphql_query("27234427476213202", variables)

            clips_data = (resp.get("data") or {}).get("xdt_api__v1__clips__user__connection_v2", {})
            edges = clips_data.get("edges", [])
            page_info = clips_data.get("page_info", {})

            if not edges:
                break

            for edge in edges:
                if len(collected) >= max_items:
                    break
                media = (edge.get("node") or {}).get("media") or {}
                sc = media.get("code")
                if not sc or sc in seen:
                    continue
                seen.add(sc)

                taken_at = media.get("taken_at")
                published_at = (
                    datetime.fromtimestamp(taken_at, timezone.utc).isoformat()
                    if taken_at
                    else datetime.now(timezone.utc).isoformat()
                )

                caption_obj = media.get("caption")
                caption_text = caption_obj.get("text") if isinstance(caption_obj, dict) else None
                hashtags = re.findall(r"#(\w+)", caption_text or "")
                mentions = re.findall(r"@(\w+)", caption_text or "")

                video_versions = media.get("video_versions") or []
                video_url = video_versions[0].get("url") if video_versions else None
                candidates = (media.get("image_versions2") or {}).get("candidates") or []
                thumbnail_url = candidates[0].get("url") if candidates else None

                views = media.get("play_count")
                likes = media.get("like_count")
                comments = media.get("comment_count")
                duration = media.get("video_duration")

                collected.append({
                    "instagram_username": username,
                    "instagram_profile_id": profile_id,
                    "post_id": str(media.get("pk") or media.get("id", "")),
                    "shortcode": sc,
                    "instagram_url": f"https://www.instagram.com/reel/{sc}/",
                    "content_type": "reel",
                    "published_at": published_at,
                    "caption": caption_text,
                    "hashtags": hashtags,
                    "mentions": mentions,
                    "thumbnail_url": thumbnail_url,
                    "video_url": video_url,
                    "video_duration": float(duration) if duration else None,
                    "view_count": int(views) if views is not None and views >= 0 else None,
                    "like_count": int(likes) if likes is not None and likes >= 0 else None,
                    "comment_count": int(comments) if comments is not None and comments >= 0 else None,
                    "share_count": None,
                    "save_count": None,
                    "first_discovered_at": datetime.now(timezone.utc).isoformat(),
                    "last_scraped_at": datetime.now(timezone.utc).isoformat(),
                })

            has_next = page_info.get("has_next_page", False)
            cursor = page_info.get("end_cursor")
            if not cursor or cursor == prev_cursor or not has_next:
                break
            prev_cursor = cursor
            time.sleep(SCRAPE_DELAY)

        except Exception as e:
            logger.warning(f"Clips page failed for @{username} (cursor={cursor}): {e}")
            break

    return collected


# ── VPS push ──────────────────────────────────────────────────────────────────

def push_to_vps(competitor_id: str, data: dict) -> bool:
    """POSTs scraped data to the VPS ingest endpoint."""
    url = f"{VPS_API_URL.rstrip('/')}/competitors/{competitor_id}/ingest"
    try:
        r = requests.post(url, json=data, timeout=30)
        r.raise_for_status()
        resp = r.json()
        logger.info(f"  ✓ VPS accepted: {resp.get('message', 'ok')}")
        return True
    except Exception as e:
        logger.error(f"  ✗ Failed to push to VPS: {e}")
        return False


def get_competitors_from_vps() -> list:
    """Fetches the competitor list from the VPS API."""
    url = f"{VPS_API_URL.rstrip('/')}/competitors"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Could not fetch competitors from VPS: {e}")
        return []


# ── Background scrape runner ──────────────────────────────────────────────────

_scrape_status = {"running": False, "last_run": None, "results": {}}


def run_scrape_session():
    """Runs a full scrape of all competitors in a background thread."""
    global _scrape_status
    if _scrape_status["running"]:
        logger.info("Scrape already in progress — skipping.")
        return

    def _work():
        _scrape_status["running"] = True
        _scrape_status["results"] = {}
        logger.info("=== Scrape session started from residential IP ===")

        loader = build_loader()
        competitors = get_competitors_from_vps()
        active = [c for c in competitors if c.get("status", "active") == "active"]

        logger.info(f"Competitors to scrape: {[c['username'] for c in active]}")

        for comp in active:
            uid = comp["id"]
            username = comp["username"]
            try:
                data = scrape_competitor(loader, comp, MAX_REELS)
                ok = push_to_vps(uid, data)
                _scrape_status["results"][username] = "ok" if ok else "push_failed"
            except Exception as e:
                logger.error(f"Error scraping @{username}: {e}")
                _scrape_status["results"][username] = f"error: {e}"
            time.sleep(3)

        _scrape_status["running"] = False
        _scrape_status["last_run"] = datetime.now().strftime("%H:%M:%S")
        logger.info(f"=== Scrape session complete: {_scrape_status['results']} ===")

    t = threading.Thread(target=_work, daemon=True)
    t.start()


# ── Flask server ──────────────────────────────────────────────────────────────

app = Flask("contentoutlier-agent")

CORS(app, origins=[
    "https://contentoutlier.mytaskengine.com",
    "http://localhost:3000",
    "http://localhost:3003",
    "http://localhost:9191",
])


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "vps": VPS_API_URL,
        "configured_user": _current_creds.get("username"),
    })


@app.post("/scrape")
def trigger_scrape():
    """Called by the platform when you open it in your browser."""
    run_scrape_session()
    return jsonify({
        "status": "started",
        "message": "Scraping from your residential connection. Results will appear on the platform shortly.",
    })


@app.get("/status")
def status():
    return jsonify(_scrape_status)


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("  ContentOutlier Residential Scraping Agent")
    logger.info(f"  Listening on http://localhost:{AGENT_PORT}")
    logger.info(f"  Pushing to:    {VPS_API_URL}")
    logger.info("  Scrapes trigger automatically when you open the platform")
    logger.info("=" * 60)
    app.run(host="127.0.0.1", port=AGENT_PORT, debug=False, use_reloader=False)
