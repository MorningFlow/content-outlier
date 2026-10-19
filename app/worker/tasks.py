import logging
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
import instaloader
from sqlalchemy.orm import Session
from app.models.competitor import Competitor
from app.models.content import Content
from app.models.job import ScrapeJob, ProcessingJob
from app.scraper.collector import InstagramCollector
from app.scraper.exceptions import RateLimitException, ScraperException
from app.services.content_service import ContentService
from app.services.transcription_service import TranscriptionService
from app.storage import get_storage
from app.config import settings

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Executes background jobs including profile scraping, media downloads, and transcription."""

    def __init__(self, db: Session, collector: InstagramCollector | None = None):
        self.db = db
        self.collector = collector or InstagramCollector()
        self.content_service = ContentService(db)
        self.transcription_service = TranscriptionService(db)
        self.storage = get_storage()

    def process_scrape_job(self, job: ScrapeJob):
        """Processes initial or incremental profile scrape jobs."""
        competitor = self.db.query(Competitor).filter(Competitor.id == job.competitor_id).first()
        if not competitor:
            raise ValueError(f"Competitor not found for scrape job {job.id}")

        now = datetime.now(timezone.utc)
        if competitor.rate_limited_until and competitor.rate_limited_until.replace(tzinfo=timezone.utc) > now:
            raise RateLimitException(f"Account @{competitor.username} is currently in rate limit cooldown.")

        logger.info(f"Executing {job.job_type} for @{competitor.username}")

        def update_progress(stage: str, percent: int):
            try:
                job.progress_stage = stage
                job.progress_percent = min(100, max(0, percent))
                self.db.commit()
            except Exception as e:
                logger.debug(f"Progress update error: {e}")

        try:
            # Seed shortcodes from job payload only (e.g. explicitly passed Reel URL during onboarding)
            seed_codes = list((job.payload or {}).get("seed_shortcodes") or [])
            seed_sc = (job.payload or {}).get("seed_shortcode")
            if seed_sc and seed_sc not in seed_codes:
                seed_codes.append(seed_sc)

            # Query existing database shortcodes for this competitor
            existing_shortcodes = set(
                c[0] for c in self.db.query(Content.shortcode).filter(Content.competitor_id == competitor.id).all() if c[0]
            )

            # Filter seed_codes so we never re-seed shortcodes already in our database
            seed_codes = [sc for sc in seed_codes if sc not in existing_shortcodes]

            if seed_codes:
                self.collector._shortcode_cache.setdefault(competitor.username, [])
                for sc in seed_codes:
                    if sc not in self.collector._shortcode_cache[competitor.username]:
                        self.collector._shortcode_cache[competitor.username].append(sc)

            if competitor.instagram_id:
                self.collector._user_id_cache[competitor.username] = competitor.instagram_id

            update_progress(f"Resolving profile for @{competitor.username}...", 10)

            # 1. Resolve Profile
            profile_info = self.collector.resolve_profile(
                competitor.username,
                on_progress=update_progress,
            )
            if profile_info.get("instagram_id"):
                competitor.instagram_id = profile_info.get("instagram_id")
            if profile_info.get("profile_name") and profile_info.get("profile_name") != competitor.username:
                competitor.profile_name = profile_info.get("profile_name")
            elif profile_info.get("profile_name") and not competitor.profile_name:
                competitor.profile_name = profile_info.get("profile_name")
            if profile_info.get("profile_image") and not competitor.profile_image:
                competitor.profile_image = profile_info.get("profile_image")
            if profile_info.get("followers") is not None:
                competitor.followers = profile_info.get("followers")
            competitor.scrape_error = None
            competitor.rate_limited_until = None
            self.db.commit()

            update_progress(f"Profile found ({competitor.followers or 0:,} followers). Getting profile picture...", 25)

            # Update profile image from local storage if available
            local_profile_path = settings.storage_path / "profiles" / f"{competitor.username}.jpg"
            if local_profile_path.exists() and local_profile_path.stat().st_size > 0:
                competitor.profile_image = f"/media/profiles/{competitor.username}.jpg"
                self.db.commit()

            # 2. Fetch Reels and Videos
            # Determine whether this is an initial scan or an incremental sync after first run
            latest_post = (
                self.db.query(Content)
                .filter(Content.competitor_id == competitor.id)
                .order_by(Content.published_at.desc())
                .first()
            )
            is_incremental = latest_post is not None
            since_timestamp = latest_post.published_at if latest_post else None
            latest_shortcode = latest_post.shortcode if latest_post else None

            # Incremental sync only queries for newly posted reels (small batch), not 50
            max_reels = 12 if is_incremental else settings.MAX_REELS_PER_SCRAPE
            cutoff_days = settings.SCRAPE_DAYS_CUTOFF
            if is_incremental and latest_post and latest_post.published_at:
                update_progress(f"Checking for new Reels published since {latest_post.published_at.strftime('%b %d')}...", 35)
            else:
                update_progress(f"Querying Instagram Reels (last {cutoff_days} days)...", 35)

            items = self.collector.fetch_reels_and_videos(
                competitor.username,
                max_items=max_reels,
                days_cutoff=cutoff_days,
                existing_shortcodes=existing_shortcodes,
                since_timestamp=since_timestamp,
                latest_shortcode=latest_shortcode,
                on_progress=update_progress,
            )
            logger.info(f"Collected {len(items)} Reels/videos for @{competitor.username} (incremental={is_incremental})")

            # 3. Ingest items, save historical snapshots, compute baselines and outliers
            if items:
                update_progress(f"Analyzing {len(items)} new posts and calculating performance baselines...", 88)
                self.content_service.ingest_scraped_items(competitor.id, items)
                competitor.last_scraped_at = datetime.now(timezone.utc)
                competitor.status = "active"
                self.db.commit()
                update_progress(f"Completed! {len(items)} new posts tracked and baselines updated.", 100)
            elif not items:
                competitor.last_scraped_at = datetime.now(timezone.utc)
                competitor.status = "active"
                competitor.scrape_error = None
                self.db.commit()
                if existing_shortcodes:
                    # Refresh outlier velocity and baseline medians for existing tracked posts
                    self.content_service.recalculate_competitor_intelligence(competitor.id)
                    update_progress(f"Completed! All posts are up to date ({len(existing_shortcodes)} posts already tracked).", 100)
                else:
                    update_progress(f"Completed! No public Reels found in the last {cutoff_days} days.", 100)

        except ScraperException as e:
            if competitor.status != "needs_auth":
                competitor.status = "error"
            competitor.scrape_error = str(e)
            job.progress_stage = f"Action needed: {e}"
            self.db.commit()
            raise
        except RateLimitException as e:
            competitor.status = "rate_limited"
            competitor.rate_limited_until = now + timedelta(seconds=e.retry_after_seconds)
            competitor.scrape_error = str(e)
            job.progress_stage = f"Rate limited: {e}"
            self.db.commit()
            raise
        except Exception as e:
            if competitor.status != "needs_auth":
                competitor.status = "error"
            competitor.scrape_error = str(e)
            job.progress_stage = f"Failed: {e}"
            self.db.commit()
            raise

    def process_processing_job(self, job: ProcessingJob):
        """Processes video downloads and transcription pipelines."""
        content = self.db.query(Content).filter(Content.id == job.content_id).first()
        if not content:
            raise ValueError(f"Content not found for processing job {job.id}")

        if job.job_type == "video_download":
            self._download_video(content)
        elif job.job_type == "transcription":
            self._transcribe_video(content)
        else:
            raise ValueError(f"Unknown processing job type: {job.job_type}")

    def _download_video(self, content: Content):
        """Downloads Reel MP4 and thumbnail and uploads to abstract storage layer."""
        if not content.video_url and content.shortcode:
            try:
                p = instaloader.Post.from_shortcode(self.collector.loader.context, content.shortcode)
                content.video_url = p.video_url
                if not content.thumbnail_url:
                    content.thumbnail_url = p.url
            except Exception as e:
                logger.warning(f"Could not resolve video_url on demand for {content.shortcode}: {e}")

        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            video_file, thumb_file = self.collector.download_media_files(
                video_url=content.video_url,
                thumbnail_url=content.thumbnail_url,
                shortcode=content.shortcode,
                tmp_dir=tmp_dir,
            )

            if video_file and video_file.is_file():
                rel_video = f"videos/{content.instagram_username}/{content.shortcode}.mp4"
                self.storage.save_file(video_file, rel_video, content_type="video/mp4")
                content.video_path = rel_video
                content.download_status = "downloaded"

            if thumb_file and thumb_file.is_file():
                rel_thumb = f"thumbnails/{content.instagram_username}/{content.shortcode}.jpg"
                self.storage.save_file(thumb_file, rel_thumb, content_type="image/jpeg")
                content.thumbnail_path = rel_thumb

            if not video_file and not thumb_file:
                content.download_status = "failed"

            self.db.commit()

    def _transcribe_video(self, content: Content):
        """Runs the transcription pipeline for the content item."""
        transcript = self.transcription_service.transcribe_content(content.id)
        if not transcript:
            content.transcription_status = "failed"
            self.db.commit()
            raise RuntimeError(f"Transcription failed for content {content.id}")
