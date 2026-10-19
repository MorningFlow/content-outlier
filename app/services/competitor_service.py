import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.competitor import Competitor
from app.models.content import Content
from app.models.job import ScrapeJob
from app.schemas.competitor import CompetitorCreate, CompetitorUpdate, CompetitorResponse
from app.schemas.job import JobResponse

logger = logging.getLogger(__name__)


class CompetitorService:
    """Handles competitor lifecycle, validation, status changes, and sync orchestration."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, competitor_id: str) -> Optional[Competitor]:
        return self.db.query(Competitor).filter(Competitor.id == competitor_id).first()

    def get_by_username(self, username: str) -> Optional[Competitor]:
        clean = username.strip().lstrip("@").lower()
        return self.db.query(Competitor).filter(Competitor.username == clean).first()

    def list_competitors(self) -> list[CompetitorResponse]:
        """Lists competitors annotated with current tracked content counts and active sync jobs."""
        competitors = self.db.query(Competitor).order_by(Competitor.created_at.desc()).all()
        results = []
        now = datetime.now(timezone.utc)
        for comp in competitors:
            count = self.db.query(func.count(Content.id)).filter(Content.competitor_id == comp.id).scalar() or 0
            comp_resp = CompetitorResponse.model_validate(comp)
            comp_resp.content_count = count

            # Find active or recently finished job
            active_job = self.db.query(ScrapeJob).filter(
                ScrapeJob.competitor_id == comp.id,
                ScrapeJob.status.in_(["queued", "running"])
            ).order_by(ScrapeJob.created_at.desc()).first()

            if not active_job:
                recent_job = self.db.query(ScrapeJob).filter(
                    ScrapeJob.competitor_id == comp.id,
                    ScrapeJob.status.in_(["completed", "failed"])
                ).order_by(ScrapeJob.created_at.desc()).first()
                if recent_job and recent_job.completed_at:
                    c_at = recent_job.completed_at if recent_job.completed_at.tzinfo else recent_job.completed_at.replace(tzinfo=timezone.utc)
                    if (now - c_at).total_seconds() < 12:
                        active_job = recent_job

            if active_job:
                comp_resp.active_job = JobResponse.model_validate(active_job)

            results.append(comp_resp)
        return results

    def create_competitor(self, data: CompetitorCreate) -> tuple[CompetitorResponse, ScrapeJob]:
        """Adds competitor and automatically queues an initial sync background job.
        Supports plain usernames (@nivedan.ai), profile URLs, or Reel/post URLs (shortcode anchor).
        """
        import re
        import instaloader

        raw_input = data.username.strip()
        clean_username = raw_input.lstrip("@").lower()
        seed_shortcode = None
        discovered_id = None
        discovered_name = None

        # Check if user entered a Reel/Post URL or shortcode
        # e.g., https://www.instagram.com/reel/DPEVM0oCQKE/ or instagram.com/p/DPEVM0oCQKE
        reel_match = re.search(r"/(?:reel|p)/([A-Za-z0-9_-]+)", raw_input)
        discovered_avatar = None
        if reel_match:
            seed_shortcode = reel_match.group(1)
            try:
                loader = instaloader.Instaloader()
                if hasattr(loader.context, "_rate_controller"):
                    loader.context._rate_controller.handle_429 = lambda query_type: None
                    loader.context._rate_controller.sleep = lambda secs: None
                post = instaloader.Post.from_shortcode(loader.context, seed_shortcode)
                clean_username = post.owner_username.lower()
                discovered_id = str(post.owner_id)
                node = getattr(post, "_node", {}) or {}
                discovered_name = (node.get("owner") or {}).get("full_name") or (node.get("user") or {}).get("full_name") or post.owner_username
                pic_url = (node.get("user") or {}).get("profile_pic_url") or (node.get("owner") or {}).get("profile_pic_url")
                if pic_url:
                    try:
                        from app.core.config import settings
                        import httpx
                        profiles_dir = settings.storage_path / "profiles"
                        profiles_dir.mkdir(parents=True, exist_ok=True)
                        dest = profiles_dir / f"{clean_username}.jpg"
                        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                            r = client.get(pic_url)
                            if r.status_code == 200 and len(r.content) > 100:
                                dest.write_bytes(r.content)
                                discovered_avatar = f"/media/profiles/{clean_username}.jpg"
                    except Exception as pe:
                        logger.debug(f"Failed to pre-download avatar for {clean_username}: {pe}")
                logger.info(f"Anchored @{clean_username} (ID: {discovered_id}, Name: {discovered_name}) from Reel {seed_shortcode}")
            except Exception as e:
                logger.warning(f"Could not anchor profile from Reel URL {raw_input}: {e}")
        elif "instagram.com" in raw_input:
            profile_match = re.search(r"instagram\.com/([A-Za-z0-9_.-]+)", raw_input)
            if profile_match:
                cand = profile_match.group(1).rstrip("/").strip().lstrip("@").lower()
                if cand not in ("p", "reel", "reels", "stories", "explore"):
                    clean_username = cand

        # Zero-login discovery: resolve numeric user ID & stats if not yet anchored
        discovered_followers = None
        if not discovered_id:
            try:
                from app.scraper.collector import InstagramCollector
                collector = InstagramCollector()
                id_data = collector._resolve_public_user_id_and_stats(clean_username)
                if id_data and id_data.get("instagram_id"):
                    discovered_id = id_data.get("instagram_id")
                    discovered_followers = id_data.get("followers")
                    logger.info(f"Zero-login pre-resolved @{clean_username} -> ID {discovered_id}, Followers {discovered_followers}")
            except Exception as e:
                logger.debug(f"Zero-login pre-resolution skipped for @{clean_username}: {e}")

        existing = self.get_by_username(clean_username)
        if existing:
            # If already exists, update anchored fields if discovered and queue sync
            if discovered_id and not existing.instagram_id:
                existing.instagram_id = discovered_id
            if discovered_name and (not existing.profile_name or existing.profile_name == clean_username):
                existing.profile_name = discovered_name
            if discovered_avatar and not existing.profile_image:
                existing.profile_image = discovered_avatar
            if discovered_followers and not existing.followers:
                existing.followers = discovered_followers
            self.db.commit()

            job_payload = {"username": clean_username}
            if seed_shortcode:
                job_payload["seed_shortcode"] = seed_shortcode
                job_payload["seed_shortcodes"] = [seed_shortcode]
            job = self.queue_sync_job(existing.id, job_type="incremental_profile_sync", payload=job_payload)
            count = self.db.query(func.count(Content.id)).filter(Content.competitor_id == existing.id).scalar() or 0
            resp = CompetitorResponse.model_validate(existing)
            resp.content_count = count
            resp.active_job = JobResponse.model_validate(job)
            return resp, job

        competitor = Competitor(
            username=clean_username,
            instagram_id=discovered_id,
            profile_name=discovered_name or clean_username,
            profile_image=discovered_avatar,
            followers=discovered_followers,
            status="active",
        )
        self.db.add(competitor)
        self.db.flush()

        job_payload = {"username": clean_username}
        if seed_shortcode:
            job_payload["seed_shortcode"] = seed_shortcode
            job_payload["seed_shortcodes"] = [seed_shortcode]

        job = ScrapeJob(
            job_type="initial_profile_sync",
            status="queued",
            progress_percent=0,
            progress_stage="Queued for synchronization...",
            competitor_id=competitor.id,
            scheduled_at=datetime.now(timezone.utc),
            payload=job_payload,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(competitor)
        self.db.refresh(job)

        resp = CompetitorResponse.model_validate(competitor)
        resp.content_count = 0
        resp.active_job = JobResponse.model_validate(job)
        return resp, job

    def update_competitor(self, competitor_id: str, data: CompetitorUpdate) -> Optional[CompetitorResponse]:
        competitor = self.get_by_id(competitor_id)
        if not competitor:
            return None

        if data.status is not None:
            competitor.status = data.status
        if data.profile_name is not None:
            competitor.profile_name = data.profile_name

        self.db.commit()
        self.db.refresh(competitor)

        count = self.db.query(func.count(Content.id)).filter(Content.competitor_id == competitor.id).scalar() or 0
        resp = CompetitorResponse.model_validate(competitor)
        resp.content_count = count
        return resp

    def delete_competitor(self, competitor_id: str) -> bool:
        competitor = self.get_by_id(competitor_id)
        if not competitor:
            return False
        self.db.delete(competitor)
        self.db.commit()
        return True

    def queue_sync_job(
        self,
        competitor_id: str,
        job_type: str = "incremental_profile_sync",
        payload: Optional[dict] = None,
    ) -> ScrapeJob:
        """Enqueues a synchronization job for a competitor."""
        competitor = self.get_by_id(competitor_id)
        if not competitor:
            raise ValueError(f"Competitor {competitor_id} not found")

        job_payload = dict(payload) if payload else {"username": competitor.username}

        job = ScrapeJob(
            job_type=job_type,
            status="queued",
            progress_percent=0,
            progress_stage="Queued for synchronization...",
            competitor_id=competitor.id,
            scheduled_at=datetime.now(timezone.utc),
            payload=job_payload,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job
