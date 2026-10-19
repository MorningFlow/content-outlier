import re
import time
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Any, Callable
import httpx
import instaloader
from app.config import settings
from app.scraper.client import InstaloaderClient
from app.scraper.exceptions import (
    ScraperException,
    ProfileNotFoundException,
    PrivateProfileException,
    RateLimitException,
    CheckpointException,
)

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


class InstagramCollector:
    """Collects Instagram competitor profiles, Reels, and metadata without requiring an Instagram session key."""

    def __init__(self, client: Optional[InstaloaderClient] = None):
        self.client = client or InstaloaderClient()
        self.loader = self.client.loader
        self._shortcode_cache: dict[str, list[str]] = {}
        self._user_id_cache: dict[str, str] = {}

    def _resolve_via_instagram_search(
        self, username: str, on_progress: Optional[Callable[[str, int], None]] = None
    ) -> Optional[dict[str, Any]]:
        """Resolves profile info via Instagram's web topsearch endpoint using active session cookies.

        Tries the full username first; if no exact match is returned (common for
        dot-usernames like 'sanskarr.tiwari' where Instagram's topsearch may
        return nothing), retries with the prefix before the first dot and accepts
        any result whose username matches the full original name.
        """
        session = getattr(self.loader.context, "_session", None)
        if not session:
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "x-ig-app-id": "936619743392459",
            "Accept-Language": "en-US,en;q=0.9",
        }

        def _search(query: str) -> Optional[dict]:
            url = f"https://www.instagram.com/web/search/topsearch/?context=blended&query={query}"
            try:
                resp = session.get(url, headers=headers, timeout=12.0)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                users = data.get("users", [])
                for u in users:
                    user_info = u.get("user", {})
                    if (user_info.get("username") or "").lower() == username.lower():
                        if user_info.get("is_private"):
                            raise PrivateProfileException(f"Profile @{username} is private.")
                        pk = str(user_info.get("pk"))
                        self._user_id_cache[username] = pk
                        avatar_url = user_info.get("profile_pic_url")
                        if avatar_url:
                            local_avatar = self.download_and_save_profile_pic(username, avatar_url)
                            if local_avatar:
                                avatar_url = local_avatar
                        return {
                            "username": username,
                            "instagram_id": pk,
                            "profile_name": user_info.get("full_name") or username,
                            "profile_image": avatar_url,
                            "followers": None,
                            "is_private": False,
                            "media_count": 0,
                        }
            except (PrivateProfileException, ProfileNotFoundException):
                raise
            except Exception as e:
                logger.debug(f"Search query '{query}' failed: {e}")
            return None

        try:
            # 1. Exact username query
            result = _search(username)
            if result:
                return result

            # 2. Prefix-only query (handles dot-usernames like 'sanskarr.tiwari')
            prefix = username.split(".")[0]
            if prefix and prefix != username:
                logger.debug(f"Exact search for @{username} returned no match; retrying with prefix '{prefix}'.")
                result = _search(prefix)
                if result:
                    return result

        except (PrivateProfileException, ProfileNotFoundException):
            raise
        except Exception as e:
            logger.debug(f"Search-based profile resolution failed for @{username}: {e}")
        return None

    def _resolve_public_user_id_and_stats(self, username: str) -> Optional[dict[str, Any]]:
        """Resolves numeric user ID, follower count, and post count without login or cookies.
        Uses public Instagram viewer mirrors that expose raw var USER_ID = <id>
        and profile statistics without Cloudflare challenge roadblocks.
        """
        clean_user = username.strip().lstrip("@").lower()
        url = f"https://insta-stories-viewer.com/{clean_user}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
                r = client.get(url)
                if r.status_code == 200:
                    m = re.search(r'var\s+USER_ID\s*=\s*(\d+);', r.text)
                    if m:
                        user_id = m.group(1)
                        self._user_id_cache[clean_user] = user_id

                        # Parse followers if available
                        followers = None
                        stats_matches = re.findall(r'profile__stats-([a-z]+)">([^<]+)<', r.text)
                        for stat_name, stat_val in stats_matches:
                            if stat_name == "followers":
                                f_str = stat_val.strip().upper()
                                mult = 1
                                if "K" in f_str:
                                    mult = 1_000
                                    f_str = f_str.replace("K", "")
                                elif "M" in f_str:
                                    mult = 1_000_000
                                    f_str = f_str.replace("M", "")
                                elif "B" in f_str:
                                    mult = 1_000_000_000
                                    f_str = f_str.replace("B", "")
                                try:
                                    followers = int(float(f_str.replace(",", "")) * mult)
                                except Exception:
                                    pass

                        logger.info(f"Zero-login public resolution succeeded for @{clean_user}: ID={user_id}, Followers={followers}")
                        return {
                            "username": clean_user,
                            "instagram_id": user_id,
                            "followers": followers,
                        }
        except Exception as e:
            logger.debug(f"Public user ID resolution failed for @{clean_user}: {e}")
        return None

    def resolve_profile(self, username: str, on_progress: Optional[Callable[[str, int], None]] = None) -> dict[str, Any]:
        """Resolves an Instagram username and returns profile metadata.
        Uses zero-login public ID discovery, post anchors, and authenticated search when available.
        """
        clean_username = username.strip().lstrip("@").lower()
        logger.info(f"Resolving Instagram profile: @{clean_username}")
        if on_progress:
            on_progress(f"Connecting to Instagram for @{clean_username}...", 10)

        # If logged in with session, attempt search-based resolution first, then official Instaloader flow
        if getattr(self.loader.context, "is_logged_in", False):
            # 1. Search resolution endpoint (bypasses 429 on web_profile_info)
            search_res = self._resolve_via_instagram_search(clean_username, on_progress=on_progress)
            if search_res:
                return search_res

            # 2. Official Instaloader Profile.from_username
            try:
                if on_progress:
                    on_progress(f"Fetching official profile metadata for @{clean_username}...", 15)
                profile = instaloader.Profile.from_username(self.loader.context, clean_username)
                if profile.is_private:
                    raise PrivateProfileException(f"Profile @{clean_username} is private.")

                return {
                    "username": clean_username,
                    "instagram_id": str(profile.userid) if profile.userid else None,
                    "profile_name": profile.full_name or clean_username,
                    "profile_image": profile.profile_pic_url,
                    "followers": profile.followers,
                    "is_private": profile.is_private,
                    "media_count": profile.mediacount,
                }
            except (ProfileNotFoundException, PrivateProfileException):
                raise
            except Exception as e:
                logger.info(f"Logged-in profile resolution failed ({e}); falling back to zero-login public resolution.")

        # Zero-login discovery: resolve numeric user ID & stats
        user_id = self._user_id_cache.get(clean_username)
        public_stats = None
        if not user_id:
            if on_progress:
                on_progress(f"Resolving numeric Instagram ID for @{clean_username}...", 15)
            public_stats = self._resolve_public_user_id_and_stats(clean_username)
            if public_stats and public_stats.get("instagram_id"):
                user_id = public_stats.get("instagram_id")

        # If seed shortcodes are available in cache, resolve author metadata directly from post node
        if not user_id:
            cached_codes = self._shortcode_cache.get(clean_username, [])
            if cached_codes:
                try:
                    test_post = instaloader.Post.from_shortcode(self.loader.context, cached_codes[0])
                    if test_post.owner_id:
                        user_id = str(test_post.owner_id)
                        self._user_id_cache[clean_username] = user_id
                except Exception as e:
                    logger.debug(f"Could not resolve author from cached seed shortcode: {e}")

        # If user_id is now known, query Instagram's first clip to anchor full name and avatar!
        if user_id:
            followers = public_stats.get("followers") if public_stats else None
            local_pic_file = settings.storage_path / "profiles" / f"{clean_username}.jpg"
            if local_pic_file.exists() and local_pic_file.stat().st_size > 0:
                return {
                    "username": clean_username,
                    "instagram_id": user_id,
                    "profile_name": clean_username,
                    "profile_image": f"/media/profiles/{clean_username}.jpg",
                    "followers": followers,
                    "is_private": False,
                    "media_count": 50,
                }

            try:
                if on_progress:
                    on_progress(f"Fetching verified profile data for @{clean_username}...", 20)
                vars = {"data": {"include_feed_video": True, "page_size": 1, "target_user_id": user_id}}
                resp = self.loader.context.doc_id_graphql_query("27234427476213202", vars)
                edges = (resp.get("data") or {}).get("xdt_api__v1__clips__user__connection_v2", {}).get("edges", [])
                if edges:
                    first_code = (edges[0].get("node") or {}).get("media", {}).get("code")
                    if first_code:
                        self._shortcode_cache.setdefault(clean_username, [])
                        if first_code not in self._shortcode_cache[clean_username]:
                            self._shortcode_cache[clean_username].append(first_code)
                        test_post = instaloader.Post.from_shortcode(self.loader.context, first_code)
                        node = getattr(test_post, "_node", {}) or {}
                        p_name = (node.get("owner") or {}).get("full_name") or (node.get("user") or {}).get("full_name") or test_post.owner_username
                        pic = (node.get("user") or {}).get("profile_pic_url") or (node.get("owner") or {}).get("profile_pic_url")
                        local_pic = self.download_and_save_profile_pic(clean_username, pic) if pic else None
                        return {
                            "username": clean_username,
                            "instagram_id": user_id,
                            "profile_name": p_name or clean_username,
                            "profile_image": local_pic or pic,
                            "followers": followers,
                            "is_private": False,
                            "media_count": 50,
                        }
            except Exception as e:
                logger.debug(f"Clips query profile metadata extraction failed for @{clean_username}: {e}")

            return {
                "username": clean_username,
                "instagram_id": user_id,
                "profile_name": clean_username,
                "profile_image": None,
                "followers": followers,
                "is_private": False,
                "media_count": 0,
            }

        # Fallback to unauthenticated public mirror
        return self._resolve_public_profile(clean_username, on_progress=on_progress)

    def _resolve_public_profile(self, username: str, on_progress: Optional[Callable[[str, int], None]] = None) -> dict[str, Any]:
        """Resolves public profile metadata and discovers recent shortcodes without session key."""
        url = f"https://imginn.com/{username}/"
        if on_progress:
            on_progress(f"Querying profile metadata for @{username}...", 15)
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True, headers=DEFAULT_HEADERS) as http_client:
                resp = http_client.get(url)
                if resp.status_code == 404:
                    raise ProfileNotFoundException(f"Instagram profile '{username}' does not exist.")
                if resp.status_code == 429:
                    raise RateLimitException("Instagram mirror rate limit exceeded.")
                if resp.status_code == 403:
                    logger.warning(f"Public profile mirror returned 403 Forbidden for @{username}; using fallback profile metadata.")
                    return {
                        "username": username,
                        "instagram_id": self._user_id_cache.get(username),
                        "profile_name": username,
                        "profile_image": None,
                        "followers": None,
                        "is_private": False,
                        "media_count": 0,
                    }
                if resp.status_code != 200:
                    logger.warning(f"Public profile mirror returned HTTP {resp.status_code} for @{username}")

                html = resp.text

                # Parse profile name
                title_m = re.search(r'<title>(.*?)(?:\(@|\s*-\s*Imginn)', html)
                profile_name = title_m.group(1).strip() if title_m else username

                # Parse followers
                followers = None
                desc_m = re.search(r'<meta name="description" content="([^"]+)"', html)
                if desc_m:
                    f_match = re.search(r'([\d\.,]+[KMBkmb]?)\s+Followers', desc_m.group(1))
                    if f_match:
                        f_str = f_match.group(1).upper()
                        mult = 1
                        if "K" in f_str:
                            mult = 1_000
                            f_str = f_str.replace("K", "")
                        elif "M" in f_str:
                            mult = 1_000_000
                            f_str = f_str.replace("M", "")
                        elif "B" in f_str:
                            mult = 1_000_000_000
                            f_str = f_str.replace("B", "")
                        try:
                            followers = int(float(f_str.replace(",", "")) * mult)
                        except Exception:
                            pass

                # Parse avatar
                avatar_url = None
                avatar_m = re.search(r'<div class="avatar"[^>]*>.*?<img[^>]+src="([^"]+)"', html, re.DOTALL)
                if avatar_m:
                    avatar_url = avatar_m.group(1)
                    if on_progress:
                        on_progress(f"Downloading profile picture for @{username}...", 22)
                    local_avatar = self.download_and_save_profile_pic(username, avatar_url)
                    if local_avatar:
                        avatar_url = local_avatar

                # Extract and cache shortcodes
                found_codes = re.findall(r'href="/p/([^"/]+)/"', html)
                unique_sc = []
                seen = set()
                for sc in found_codes:
                    if sc not in seen:
                        seen.add(sc)
                        unique_sc.append(sc)
                if unique_sc:
                    self._shortcode_cache[username] = unique_sc

                return {
                    "username": username,
                    "instagram_id": self._user_id_cache.get(username),
                    "profile_name": profile_name,
                    "profile_image": avatar_url,
                    "followers": followers,
                    "is_private": False,
                    "media_count": len(unique_sc),
                }

        except (ProfileNotFoundException, RateLimitException, ScraperException):
            raise
        except Exception as e:
            logger.warning(f"Error resolving public profile @{username}: {e}")
            return {
                "username": username,
                "instagram_id": self._user_id_cache.get(username),
                "profile_name": username,
                "profile_image": None,
                "followers": None,
                "is_private": False,
                "media_count": 0,
            }

    def fetch_reels_and_videos(
        self,
        username: str,
        max_items: int = 50,
        days_cutoff: Optional[int] = None,
        existing_shortcodes: Optional[set[str]] = None,
        since_timestamp: Optional[datetime] = None,
        latest_shortcode: Optional[str] = None,
        on_progress: Optional[Callable[[str, int], None]] = None,
    ) -> list[dict[str, Any]]:
        """Scrapes recent Reels and video posts from an account within the cutoff window.

        When an authenticated session is present the Profile.from_username path is
        intentionally skipped because it always hits /api/v1/users/web_profile_info/
        which the VPS datacenter IP gets 429'd on immediately.  Instead we jump
        straight to the clips GraphQL pipeline and pass the authenticated
        requests.Session so Instagram allows full pagination (>4 pages).
        """
        clean_username = username.strip().lstrip("@").lower()
        effective_days = days_cutoff if days_cutoff is not None else settings.SCRAPE_DAYS_CUTOFF
        logger.info(f"Fetching posts for @{clean_username} (max={max_items}, cutoff={effective_days} days, incremental={'yes' if since_timestamp else 'no'})")
        if on_progress:
            on_progress(f"Connecting to Instagram feeds for @{clean_username}...", 30)

        # When a session is active, skip Profile.from_username (always 429s on this
        # datacenter IP) and go straight to the authenticated clips GraphQL pipeline.
        if getattr(self.loader.context, "is_logged_in", False):
            auth_session = getattr(self.loader.context, "_session", None)
            logger.info(
                f"Logged-in session detected for @{clean_username}; using authenticated GraphQL pipeline."
            )
            return self._fetch_reels_graphql(
                clean_username,
                max_items=max_items,
                days_cutoff=effective_days,
                existing_shortcodes=existing_shortcodes,
                since_timestamp=since_timestamp,
                latest_shortcode=latest_shortcode,
                on_progress=on_progress,
                auth_session=auth_session,
            )

        # Unauthenticated fallback
        return self._fetch_reels_graphql(
            clean_username,
            max_items=max_items,
            days_cutoff=effective_days,
            existing_shortcodes=existing_shortcodes,
            since_timestamp=since_timestamp,
            latest_shortcode=latest_shortcode,
            on_progress=on_progress,
        )

    def _fetch_reels_unauthenticated(self, username: str, max_items: int = 50) -> list[dict[str, Any]]:
        """Backwards compatibility alias for unauthenticated clips fetching."""
        return self._fetch_reels_graphql(username, max_items=max_items)

    def _fetch_reels_graphql(
        self,
        username: str,
        max_items: int = 50,
        days_cutoff: Optional[int] = None,
        existing_shortcodes: Optional[set[str]] = None,
        since_timestamp: Optional[datetime] = None,
        latest_shortcode: Optional[str] = None,
        on_progress: Optional[Callable[[str, int], None]] = None,
        auth_session=None,
    ) -> list[dict[str, Any]]:
        """Fetches Reels via Instagram's clips GraphQL endpoint.

        When *auth_session* (a requests.Session with valid cookies) is provided
        the pagination requests are made directly through that session instead of
        Instaloader's anonymous context, which avoids the 401/429 that Instagram
        applies after ~4 unauthenticated pages.
        """
        collected_items = []
        seen_shortcodes = set()

        # Step A: Discover numeric profile_id and shortcodes
        profile_id = self._user_id_cache.get(username)
        shortcodes = self._shortcode_cache.get(username, [])

        if not profile_id:
            try:
                id_data = self._resolve_public_user_id_and_stats(username)
                if id_data and id_data.get("instagram_id"):
                    profile_id = id_data.get("instagram_id")
                    self._user_id_cache[username] = profile_id
            except Exception as e:
                logger.debug(f"Zero-login public user ID lookup skipped during reels fetch: {e}")

        if not shortcodes and not profile_id:
            try:
                self._resolve_public_profile(username)
            except Exception as e:
                logger.debug(f"Public profile mirror lookup skipped during reels fetch: {e}")
            shortcodes = self._shortcode_cache.get(username, [])
            profile_id = self._user_id_cache.get(username)

        # Step A2: When authenticated and profile_id is still missing, try the search endpoint
        # directly. This is the critical path for dot-usernames (e.g. 'sanskarr.tiwari') that
        # fail the public mirror and don't have a cached ID from resolve_profile.
        if not profile_id and auth_session is not None:
            logger.info(f"No cached profile_id for @{username}; attempting authenticated search resolution.")
            try:
                search_res = self._resolve_via_instagram_search(username)
                if search_res:
                    profile_id = search_res.get("instagram_id")
                    logger.info(f"Search resolution succeeded for @{username}: profile_id={profile_id}")
            except Exception as e:
                logger.debug(f"Authenticated search resolution failed for @{username}: {e}")

        # Step B: Discover profile_id from cache or first available post
        if not profile_id:
            for sc in shortcodes:
                try:
                    post = instaloader.Post.from_shortcode(self.loader.context, sc)
                    user_node = getattr(post, "_node", {}).get("user", {})
                    pic_url = user_node.get("profile_pic_url")
                    if pic_url:
                        self.download_and_save_profile_pic(username, pic_url)

                    if post.owner_id:
                        profile_id = str(post.owner_id)
                        self._user_id_cache[username] = profile_id
                        if post.is_video:
                            item_data = self._extract_post_metadata(post, username, profile_id)
                            if item_data and sc not in seen_shortcodes:
                                collected_items.append(item_data)
                                seen_shortcodes.add(sc)
                        break
                except Exception as e:
                    logger.debug(f"Could not load initial post {sc}: {e}")

        cutoff_days = days_cutoff if days_cutoff is not None else settings.SCRAPE_DAYS_CUTOFF
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
        existing_codes = set(existing_shortcodes or [])
        since_ts = (
            (since_timestamp if since_timestamp.tzinfo else since_timestamp.replace(tzinfo=timezone.utc))
            if since_timestamp
            else None
        )
        boundary_hit = False

        # Check if local profile picture exists; if missing, fetch authentic CDN pic from first new post
        local_pic = settings.storage_path / "profiles" / f"{username}.jpg"
        candidate_pfp_codes = [sc for sc in shortcodes if sc not in existing_codes]
        if not (local_pic.exists() and local_pic.stat().st_size > 0) and candidate_pfp_codes:
            try:
                test_post = instaloader.Post.from_shortcode(self.loader.context, candidate_pfp_codes[0])
                u_pic = getattr(test_post, "_node", {}).get("user", {}).get("profile_pic_url")
                if u_pic:
                    self.download_and_save_profile_pic(username, u_pic)
            except Exception:
                pass

        # Step C: If profile_id is known, paginate via Instagram's clips GraphQL endpoint.
        # When auth_session is available we POST directly with cookies to avoid the
        # anonymous rate-limit (~4 pages / 48 posts) Instagram enforces on the VPS IP.

        if profile_id and len(collected_items) < max_items:
            cursor = None
            has_next_page = True
            page_size = 12
            previous_cursor = None

            graphql_url = "https://www.instagram.com/graphql/query"
            graphql_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "x-ig-app-id": "936619743392459",
                "Accept-Language": "en-US,en;q=0.9",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.instagram.com/",
            }

            while has_next_page and len(collected_items) < max_items:
                try:
                    variables = {
                        "data": {
                            "include_feed_video": True,
                            "page_size": page_size,
                            "target_user_id": profile_id,
                        }
                    }
                    if cursor:
                        variables["data"]["max_id"] = cursor
                        variables["data"]["after"] = cursor

                    if auth_session is not None:
                        # Authenticated path: POST with session cookies for full pagination
                        post_data = {
                            "doc_id": "27234427476213202",
                            "variables": json.dumps(variables),
                        }
                        raw = auth_session.post(
                            graphql_url,
                            data=post_data,
                            headers=graphql_headers,
                            timeout=15.0,
                        )
                        if raw.status_code == 401 or "require_login" in raw.text:
                            logger.info("Instagram session expired during clips pagination; attempting auto-renewal...")
                            from app.services.instagram_auth_service import InstagramAuthService
                            renew_ok, _ = InstagramAuthService.auto_renew()
                            if renew_ok:
                                auth_session = getattr(self.loader.context, "_session", None)
                                raw = auth_session.post(
                                    graphql_url,
                                    data=post_data,
                                    headers=graphql_headers,
                                    timeout=15.0,
                                )
                        raw.raise_for_status()
                        resp = raw.json()
                    else:
                        resp = self.loader.context.doc_id_graphql_query("27234427476213202", variables)

                    clips_data = (resp.get("data") or {}).get("xdt_api__v1__clips__user__connection_v2", {})
                    edges = clips_data.get("edges", [])
                    page_info = clips_data.get("page_info", {})

                    if not edges:
                        break

                    logger.info(f"Clips query returned {len(edges)} items directly from Instagram for @{username} (total collected: {len(collected_items)})")

                    for edge in edges:
                        if len(collected_items) >= max_items:
                            break
                        media = (edge.get("node") or {}).get("media") or {}
                        sc = media.get("code")
                        if not sc or sc in seen_shortcodes:
                            continue

                        taken_at = media.get("taken_at")
                        if taken_at:
                            published_at = datetime.fromtimestamp(taken_at, timezone.utc)
                        else:
                            try:
                                pk_int = int(media.get("pk") or media.get("id"))
                                published_ms = (pk_int >> 23) + 1314220730656
                                published_at = datetime.fromtimestamp(published_ms / 1000.0, timezone.utc)
                            except Exception:
                                published_at = datetime.now(timezone.utc)

                        is_pinned = bool(media.get("clips_tab_pinned_user_ids"))

                        # 1. 30-day cutoff: clips connection is in reverse chronological order (newest first),
                        # except for pinned posts which appear at the very start regardless of age.
                        if published_at < cutoff_date:
                            if is_pinned:
                                logger.info(
                                    f"Pinned post {sc} published at {published_at.isoformat()} is older than {cutoff_days}-day cutoff. Skipping pinned post and continuing pagination."
                                )
                                continue
                            logger.info(
                                f"Post {sc} published at {published_at.isoformat()} is older than {cutoff_days}-day cutoff ({cutoff_date.isoformat()}). Halting pagination."
                            )
                            has_next_page = False
                            boundary_hit = True
                            break

                        # 2. Incremental sync boundary: stop when reaching content published at or before the latest DB post
                        if since_ts and (published_at <= since_ts or sc == latest_shortcode or (existing_codes and sc in existing_codes)):
                            if is_pinned:
                                logger.info(
                                    f"Pinned post {sc} reached incremental boundary. Skipping pinned post and continuing pagination."
                                )
                                continue
                            logger.info(
                                f"Post {sc} published at {published_at.isoformat()} reached latest DB post boundary ({since_ts.isoformat()}). Halting incremental sync."
                            )
                            has_next_page = False
                            boundary_hit = True
                            break

                        # 3. Existing database post boundary: when refilling, do not retry filling in old ones already in our DB.
                        if existing_codes and sc in existing_codes:
                            if is_pinned:
                                logger.info(f"Pinned post {sc} is already in database. Skipping pinned post.")
                                continue
                            logger.info(
                                f"Post {sc} is already in database. Reached boundary of existing items for @{username}; skipping and halting pagination."
                            )
                            boundary_hit = True
                            break

                        # Extract metrics directly from Instagram clips response
                        views = media.get("play_count")
                        if views is not None and views < 0:
                            views = None
                        likes = media.get("like_count")
                        if likes is not None and likes < 0:
                            likes = None
                        comments = media.get("comment_count")
                        if comments is not None and comments < 0:
                            comments = None

                        caption_text = (media.get("caption") or {}).get("text") if isinstance(media.get("caption"), dict) else None
                        hashtags = re.findall(r"#(\w+)", caption_text) if caption_text else []
                        mentions = re.findall(r"@(\w+)", caption_text) if caption_text else []

                        # Video & thumbnail URLs
                        video_versions = media.get("video_versions") or []
                        video_url = video_versions[0].get("url") if video_versions else None

                        candidates = (media.get("image_versions2") or {}).get("candidates") or []
                        thumbnail_url = candidates[0].get("url") if candidates else None

                        duration = media.get("video_duration")
                        if duration:
                            duration = float(duration)

                        item_data = {
                            "instagram_username": username,
                            "instagram_profile_id": profile_id,
                            "post_id": str(media.get("pk") or media.get("id")),
                            "shortcode": sc,
                            "instagram_url": f"https://www.instagram.com/reel/{sc}/",
                            "content_type": "reel",
                            "published_at": published_at,
                            "caption": caption_text,
                            "hashtags": hashtags,
                            "mentions": mentions,
                            "thumbnail_url": thumbnail_url,
                            "video_url": video_url,
                            "video_duration": duration,
                            "view_count": views,
                            "like_count": likes,
                            "comment_count": comments,
                            "share_count": None,
                            "save_count": None,
                            "first_discovered_at": datetime.now(timezone.utc),
                            "last_scraped_at": datetime.now(timezone.utc),
                        }
                        collected_items.append(item_data)
                        seen_shortcodes.add(sc)

                    if on_progress:
                        pct = min(85, 35 + int((len(collected_items) / max(max_items, 1)) * 50))
                        on_progress(f"Fetching posts & Reels ({len(collected_items)}/{max_items})...", pct)

                    if boundary_hit:
                        logger.info(f"Boundary reached (cutoff or existing database content) for @{username}; terminating clips pagination.")
                        has_next_page = False
                        break

                    has_next_page = bool(page_info.get("has_next_page"))
                    cursor = page_info.get("end_cursor")
                    if not cursor or cursor == previous_cursor:
                        break
                    previous_cursor = cursor

                    if has_next_page and len(collected_items) < max_items and settings.SCRAPE_DELAY_SECONDS > 0:
                        time.sleep(min(settings.SCRAPE_DELAY_SECONDS, 1.0))

                except Exception as e:
                    err_str = str(e).lower()
                    if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
                        logger.error(f"Instagram rate limit encountered for @{username}: {e}")
                        raise RateLimitException("Instagram rate limit encountered.", retry_after_seconds=settings.RATE_LIMIT_BACKOFF_MINUTES * 60) from e
                    logger.warning(f"Direct clips GraphQL query failed for @{username} (cursor={cursor}): {e}")
                    break

        # Step D: Fallback to direct post fetching for discovered or seeded shortcodes
        # ONLY if candidate shortcodes exist that are NOT already in the database and boundary was not reached
        all_shortcodes = list(dict.fromkeys(shortcodes + self._shortcode_cache.get(username, [])))
        candidate_shortcodes = [sc for sc in all_shortcodes if sc not in existing_codes and sc not in seen_shortcodes]

        if len(collected_items) < max_items and candidate_shortcodes and not boundary_hit:
            logger.info(f"Direct shortcode fallback triggered for @{username}: {len(candidate_shortcodes)} candidate shortcodes available.")
            for sc in candidate_shortcodes:
                if len(collected_items) >= max_items:
                    break
                try:
                    post = instaloader.Post.from_shortcode(self.loader.context, sc)
                    post_date = post.date_utc
                    if post_date.tzinfo is None:
                        post_date = post_date.replace(tzinfo=timezone.utc)
                    if post_date < cutoff_date:
                        logger.info(f"Fallback post {sc} published at {post_date.isoformat()} is older than {cutoff_days}-day cutoff. Skipping.")
                        continue
                    if since_ts and post_date <= since_ts:
                        logger.info(f"Fallback post {sc} published at {post_date.isoformat()} reached latest DB post boundary. Skipping.")
                        continue
                    if latest_shortcode and sc == latest_shortcode:
                        logger.info(f"Fallback post {sc} matches latest known shortcode. Skipping.")
                        continue

                    if not profile_id and post.owner_id:
                        profile_id = str(post.owner_id)
                        self._user_id_cache[username] = profile_id

                    if post.is_video:
                        item_data = self._extract_post_metadata(post, username, profile_id or str(post.owner_id))
                        if item_data:
                            collected_items.append(item_data)
                            seen_shortcodes.add(sc)
                            if on_progress:
                                pct = min(90, 40 + int((len(collected_items) / max(max_items, 1)) * 50))
                                on_progress(f"Fetching posts & Reels ({len(collected_items)}/{max_items})...", pct)
                except Exception as e:
                    logger.debug(f"Direct post fetch fallback failed for {sc}: {e}")

        return collected_items

    def _extract_post_metadata(self, post: instaloader.Post, username: str, profile_id: Optional[str]) -> dict[str, Any]:
        """Extracts strictly available post metadata without fabricating missing values."""
        node = getattr(post, "_node", {}) or {}

        # View count or play count (treat as NULL if absent or negative, never fabricate)
        views = None
        if post.video_view_count is not None and post.video_view_count >= 0:
            views = int(post.video_view_count)
        elif "video_play_count" in node and node["video_play_count"] is not None and node["video_play_count"] >= 0:
            views = int(node["video_play_count"])
        elif "play_count" in node and node["play_count"] is not None and node["play_count"] >= 0:
            views = int(node["play_count"])

        # Likes (NULL if hidden by Instagram user or unavailable)
        likes = None
        if post.likes is not None and post.likes >= 0:
            likes = int(post.likes)

        # Comments (NULL if unavailable)
        comments = None
        if post.comments is not None and post.comments >= 0:
            comments = int(post.comments)

        # Shares & Saves are rarely exposed publicly; only take if legitimately provided
        shares = None
        saves = None
        if "share_count" in node and node["share_count"] is not None:
            shares = int(node["share_count"])
        if "save_count" in node and node["save_count"] is not None:
            saves = int(node["save_count"])

        # Content type determination
        content_type = "reel"
        product_type = node.get("product_type", "").lower()
        if product_type == "clips" or "reel" in product_type:
            content_type = "reel"
        elif post.typename == "GraphVideo":
            content_type = "video"

        # Safe published timestamp in UTC
        published_at = post.date_utc.replace(tzinfo=timezone.utc) if post.date_utc else datetime.now(timezone.utc)

        # Hashtags and mentions
        hashtags = list(post.caption_hashtags) if post.caption_hashtags else []
        mentions = list(post.caption_mentions) if post.caption_mentions else []

        shortcode = post.shortcode
        instagram_url = f"https://www.instagram.com/reel/{shortcode}/" if content_type == "reel" else f"https://www.instagram.com/p/{shortcode}/"

        duration = None
        if hasattr(post, "video_duration") and post.video_duration:
            duration = float(post.video_duration)

        return {
            "instagram_username": username,
            "instagram_profile_id": profile_id,
            "post_id": str(post.mediaid) if post.mediaid else None,
            "shortcode": shortcode,
            "instagram_url": instagram_url,
            "content_type": content_type,
            "published_at": published_at,
            "caption": post.caption or None,
            "hashtags": hashtags,
            "mentions": mentions,
            "thumbnail_url": post.url,
            "video_url": post.video_url if post.is_video else None,
            "video_duration": duration,
            "view_count": views,
            "like_count": likes,
            "comment_count": comments,
            "share_count": shares,
            "save_count": saves,
            "first_discovered_at": datetime.now(timezone.utc),
            "last_scraped_at": datetime.now(timezone.utc),
        }

    def download_media_files(self, video_url: Optional[str], thumbnail_url: Optional[str], shortcode: str, tmp_dir: Path) -> tuple[Optional[Path], Optional[Path]]:
        """Downloads the video MP4 and thumbnail image to temporary storage with timeouts and headers."""
        tmp_dir.mkdir(parents=True, exist_ok=True)
        video_path = None
        thumb_path = None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": "https://www.instagram.com/",
        }

        with httpx.Client(timeout=60.0, follow_redirects=True, headers=headers) as client:
            if video_url:
                try:
                    resp = client.get(video_url)
                    if resp.status_code == 200:
                        v_file = tmp_dir / f"{shortcode}.mp4"
                        v_file.write_bytes(resp.content)
                        video_path = v_file
                except Exception as e:
                    logger.warning(f"Could not download video for {shortcode}: {e}")

            if thumbnail_url:
                try:
                    resp = client.get(thumbnail_url)
                    if resp.status_code == 200:
                        t_file = tmp_dir / f"{shortcode}_thumb.jpg"
                        t_file.write_bytes(resp.content)
                        thumb_path = t_file
                except Exception as e:
                    logger.warning(f"Could not download thumbnail for {shortcode}: {e}")

        return video_path, thumb_path

    def download_and_save_profile_pic(self, username: str, url: str) -> Optional[str]:
        """Downloads an authentic Instagram profile picture and saves it locally in media_storage/profiles/"""
        if not url:
            return None
        try:
            profile_dir = settings.storage_path / "profiles"
            profile_dir.mkdir(parents=True, exist_ok=True)
            local_file = profile_dir / f"{username}.jpg"
            if local_file.exists() and local_file.stat().st_size > 0:
                return f"/media/profiles/{username}.jpg"
            resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=10.0)
            if resp.status_code == 200 and len(resp.content) > 0:
                local_file.write_bytes(resp.content)
                logger.info(f"Saved authentic profile image for @{username} to {local_file}")
                return f"/media/profiles/{username}.jpg"
        except Exception as e:
            logger.warning(f"Failed to download profile image for @{username}: {e}")
        return None

