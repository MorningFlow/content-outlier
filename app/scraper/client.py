import logging
from pathlib import Path
from typing import Optional
import instaloader
from app.config import settings
from app.scraper.exceptions import (
    ScraperException,
    ProfileNotFoundException,
    PrivateProfileException,
    RateLimitException,
    CheckpointException,
    InstagramAuthException,
)

logger = logging.getLogger(__name__)


class InstaloaderClient:
    """Manages Instaloader instance, rate-limit safety, and optional session authentication."""

    def __init__(self):
        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            request_timeout=15.0,
            max_connection_attempts=1,
        )
        # Prevent Instaloader from blocking/sleeping on rate limits
        if hasattr(self.loader.context, "_rate_controller"):
            self.loader.context._rate_controller.handle_429 = lambda query_type: None
            self.loader.context._rate_controller.sleep = lambda secs: None

        # Inject proxy into Instaloader's underlying requests.Session so all
        # Instagram traffic (authenticated or not) routes through it.
        if settings.SCRAPING_PROXY:
            session = getattr(self.loader.context, "_session", None)
            if session is not None:
                proxies = {
                    "http": settings.SCRAPING_PROXY,
                    "https": settings.SCRAPING_PROXY,
                }
                session.proxies.update(proxies)
                logger.info(f"Instagram scraping proxy configured: {settings.SCRAPING_PROXY}")

        self._setup_session()

    def _setup_session(self):
        """Loads session from persistent storage, DB credentials, or environment."""
        from app.services.instagram_auth_service import InstagramAuthService

        username, password = InstagramAuthService.get_credentials()
        if not username:
            username = settings.INSTAGRAM_USERNAME

        if username:
            clean_user = username.strip().lstrip("@").lower()
            session_path = InstagramAuthService.get_session_file_path(clean_user)

            # 1. Try loading existing valid session file from storage
            if session_path.is_file():
                try:
                    self.loader.load_session_from_file(clean_user, str(session_path))
                    logger.info(f"Loaded Instagram session file for @{clean_user}")
                    return
                except Exception as e:
                    logger.warning(f"Could not load session file for @{clean_user} ({e}); will re-authenticate.")

            # 2. If password is available, log in and save fresh session
            if password:
                ok, msg = InstagramAuthService.login_and_save(clean_user, password)
                if ok and session_path.is_file():
                    try:
                        self.loader.load_session_from_file(clean_user, str(session_path))
                        logger.info(f"Authenticated and loaded fresh session for @{clean_user}")
                        return
                    except Exception as e:
                        logger.warning(f"Error loading freshly created session: {e}")

        # 3. Fallback to session cookies if configured in env
        if settings.INSTAGRAM_SESSION_ID and settings.INSTAGRAM_USERNAME:
            try:
                import urllib.parse
                raw_session_id = urllib.parse.unquote(settings.INSTAGRAM_SESSION_ID)
                cookie_dict = {
                    "sessionid": raw_session_id,
                    "ds_user_id": settings.INSTAGRAM_DS_USER_ID or settings.INSTAGRAM_USERNAME,
                    "csrftoken": settings.INSTAGRAM_CSRF_TOKEN or "dummy_csrf_token",
                }
                self.loader.context.load_session(settings.INSTAGRAM_USERNAME, cookie_dict)
                logger.info(f"Loaded Instagram session cookies for {settings.INSTAGRAM_USERNAME}")
                return
            except Exception as e:
                logger.warning(f"Failed to load Instagram session from cookies: {e}")

    def renew_session(self) -> bool:
        """Automatically renews an expired session using stored credentials and reloads it."""
        from app.services.instagram_auth_service import InstagramAuthService
        logger.info("InstaloaderClient triggered auto-renewal of Instagram session...")
        ok, msg = InstagramAuthService.auto_renew()
        if ok:
            username, _ = InstagramAuthService.get_credentials()
            if username:
                clean_user = username.strip().lstrip("@").lower()
                session_path = InstagramAuthService.get_session_file_path(clean_user)
                if session_path.is_file():
                    try:
                        self.loader.load_session_from_file(clean_user, str(session_path))
                        logger.info(f"InstaloaderClient successfully reloaded renewed session for @{clean_user}")
                        return True
                    except Exception as e:
                        logger.warning(f"Failed to reload renewed session: {e}")
        return False


    def handle_instaloader_exception(self, e: Exception, username: Optional[str] = None):
        """Maps Instaloader internal exceptions to application scraper domain exceptions."""
        error_str = str(e).lower()
        if isinstance(e, instaloader.ProfileNotExistsException):
            raise ProfileNotFoundException(f"Instagram profile '{username}' does not exist.") from e
        if isinstance(e, instaloader.PrivateProfileNotFollowedException):
            raise PrivateProfileException(f"Instagram profile '{username}' is private.") from e
        if isinstance(e, instaloader.TooManyRequestsException) or "429" in error_str or "rate limit" in error_str:
            raise RateLimitException("Instagram rate limit encountered.", retry_after_seconds=settings.RATE_LIMIT_BACKOFF_MINUTES * 60) from e
        if "checkpoint" in error_str or "challenge_required" in error_str:
            raise CheckpointException(f"Instagram security challenge triggered for {username}: {e}") from e
        raise ScraperException(f"Instagram scraper error: {e}") from e
