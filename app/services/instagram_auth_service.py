import os
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple
import instaloader
from sqlalchemy.orm import Session

from app.config import settings
from app.models.setting import AppSetting
from app.database import SessionLocal

logger = logging.getLogger("instagram_auth_service")


def get_db_setting(db: Session, key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieves a single setting value from the app_settings table."""
    try:
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        return row.value if row and row.value is not None else default
    except Exception as e:
        logger.warning(f"Failed to read setting {key} from DB: {e}")
        return default


def set_db_setting(db: Session, key: str, value: Optional[str]):
    """Persists a single setting key-value pair to the app_settings table."""
    try:
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if not row:
            row = AppSetting(key=key, value=value)
            db.add(row)
        else:
            row.value = value
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to save setting {key} to DB: {e}")
        db.rollback()


class InstagramAuthService:
    """Manages Instagram scraping credentials, active sessions, and auto-renewal."""

    @staticmethod
    def get_session_dir() -> Path:
        session_dir = settings.storage_path / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    @classmethod
    def get_session_file_path(cls, username: str) -> Path:
        clean = username.strip().lstrip("@").lower()
        return cls.get_session_dir() / f"{clean}.session"

    @classmethod
    def get_status(cls, db: Optional[Session] = None) -> dict:
        """Returns the current connection and session status."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            username = get_db_setting(db, "instagram_username") or settings.INSTAGRAM_USERNAME or ""
            status = get_db_setting(db, "instagram_status", "not_configured")
            last_login = get_db_setting(db, "instagram_last_login")
            error_message = get_db_setting(db, "instagram_error")

            has_password = bool(get_db_setting(db, "instagram_password") or settings.INSTAGRAM_PASSWORD)
            session_file = cls.get_session_file_path(username) if username else None
            has_session_file = session_file.is_file() if session_file else False

            is_configured = bool(username and (has_password or has_session_file))

            return {
                "configured": is_configured,
                "username": username if username else None,
                "status": status,
                "has_session": has_session_file,
                "last_authenticated": last_login,
                "error_message": error_message,
            }
        finally:
            if should_close:
                db.close()

    @classmethod
    def get_credentials(cls, db: Optional[Session] = None) -> Tuple[Optional[str], Optional[str]]:
        """Internal method to get username and password for scraping workers."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            username = get_db_setting(db, "instagram_username") or settings.INSTAGRAM_USERNAME or None
            password = get_db_setting(db, "instagram_password") or settings.INSTAGRAM_PASSWORD or None
            return username, password
        finally:
            if should_close:
                db.close()

    @classmethod
    def login_and_save(cls, username: str, password: str, db: Optional[Session] = None) -> Tuple[bool, str]:
        """Authenticates with Instagram via Instaloader and saves session for ongoing scraping."""
        clean_user = username.strip().lstrip("@").lower()
        if not clean_user or not password:
            return False, "Username and password are required."

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

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

        # Disable Instaloader rate controller freeze
        if hasattr(loader.context, "_rate_controller"):
            loader.context._rate_controller.handle_429 = lambda query_type: None
            loader.context._rate_controller.sleep = lambda secs: None

        session_path = cls.get_session_file_path(clean_user)

        try:
            logger.info(f"Attempting Instagram login for @{clean_user}...")
            loader.login(clean_user, password)

            # Save session file
            loader.save_session_to_file(str(session_path))
            logger.info(f"Saved Instagram session to {session_path}")

            # Update DB settings
            set_db_setting(db, "instagram_username", clean_user)
            set_db_setting(db, "instagram_password", password)
            set_db_setting(db, "instagram_session_file", str(session_path))
            set_db_setting(db, "instagram_status", "connected")
            set_db_setting(db, "instagram_last_login", datetime.now(timezone.utc).isoformat())
            set_db_setting(db, "instagram_error", None)

            return True, f"Successfully authenticated as @{clean_user}. Session active."

        except instaloader.TwoFactorAuthRequiredException:
            err = "Two-factor authentication (2FA) is enabled on this account. Please disable 2FA or generate an app session."
            set_db_setting(db, "instagram_status", "2fa_required")
            set_db_setting(db, "instagram_error", err)
            logger.warning(f"Instagram 2FA required for @{clean_user}")
            return False, err

        except instaloader.BadCredentialsException:
            err = "Incorrect Instagram username or password."
            set_db_setting(db, "instagram_status", "invalid_credentials")
            set_db_setting(db, "instagram_error", err)
            logger.warning(f"Bad credentials for @{clean_user}")
            return False, err

        except instaloader.ConnectionException as e:
            err = f"Instagram connection error: {e}"
            set_db_setting(db, "instagram_status", "connection_error")
            set_db_setting(db, "instagram_error", err)
            logger.warning(f"Connection exception for @{clean_user}: {e}")
            return False, err

        except Exception as e:
            err = f"Authentication failed: {e}"
            set_db_setting(db, "instagram_status", "error")
            set_db_setting(db, "instagram_error", err)
            logger.error(f"Login failed for @{clean_user}: {e}")
            return False, err

        finally:
            if should_close:
                db.close()

    @classmethod
    def auto_renew(cls, db: Optional[Session] = None) -> Tuple[bool, str]:
        """Automatically renews an expired session using stored credentials."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            username, password = cls.get_credentials(db)
            if not username or not password:
                return False, "No Instagram credentials stored to auto-renew."

            logger.info(f"Auto-renewing expired Instagram session for @{username}...")
            ok, msg = cls.login_and_save(username, password, db)
            if ok:
                logger.info(f"Auto-renewal succeeded for @{username}")
            else:
                logger.warning(f"Auto-renewal failed for @{username}: {msg}")
            return ok, msg
        finally:
            if should_close:
                db.close()

    @classmethod
    def save_session_cookie(
        cls,
        username: str,
        session_id: str,
        ds_user_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Tuple[bool, str]:
        """Saves session cookies directly for instant connection without password challenge."""
        clean_user = username.strip().lstrip("@").lower()
        if not clean_user or not session_id:
            return False, "Username and session ID are required."

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            import urllib.parse
            raw_sid = urllib.parse.unquote(session_id.strip())
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
            if hasattr(loader.context, "_rate_controller"):
                loader.context._rate_controller.handle_429 = lambda query_type: None
                loader.context._rate_controller.sleep = lambda secs: None

            cookie_dict = {
                "sessionid": raw_sid,
                "ds_user_id": ds_user_id or clean_user,
                "csrftoken": "dummy",
            }
            loader.context.load_session(clean_user, cookie_dict)
            session_path = cls.get_session_file_path(clean_user)
            loader.save_session_to_file(str(session_path))

            set_db_setting(db, "instagram_username", clean_user)
            set_db_setting(db, "instagram_session_file", str(session_path))
            set_db_setting(db, "instagram_status", "connected")
            set_db_setting(db, "instagram_last_login", datetime.now(timezone.utc).isoformat())
            set_db_setting(db, "instagram_error", None)

            logger.info(f"Saved Instagram session cookie for @{clean_user}")
            return True, f"Session cookie accepted. Active as @{clean_user}."
        except Exception as e:
            logger.error(f"Failed to save session cookie: {e}")
            return False, f"Could not save session: {e}"
        finally:
            if should_close:
                db.close()

    @classmethod
    def disconnect(cls, db: Optional[Session] = None) -> bool:

        """Disconnects the account and removes stored credentials and session."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            username = get_db_setting(db, "instagram_username")
            if username:
                session_path = cls.get_session_file_path(username)
                if session_path.is_file():
                    try:
                        session_path.unlink()
                    except Exception:
                        pass

            set_db_setting(db, "instagram_username", None)
            set_db_setting(db, "instagram_password", None)
            set_db_setting(db, "instagram_session_file", None)
            set_db_setting(db, "instagram_status", "not_configured")
            set_db_setting(db, "instagram_error", None)
            return True
        finally:
            if should_close:
                db.close()
