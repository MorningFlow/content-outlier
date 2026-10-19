import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc
from app.config import settings
from app.models.content import Content
from app.models.competitor import Competitor
from app.models.metric import ContentMetric
from app.models.transcript import Transcript
from app.models.job import ProcessingJob
from app.services.outlier_engine import OutlierEngine
from app.schemas.outlier import OutlierCardResponse, OutlierListResponse
from app.schemas.dashboard import DashboardResponse

logger = logging.getLogger(__name__)


class ContentService:
    """Orchestrates content persistence, historical metric snapshots, outlier scoring, and API aggregations."""

    def __init__(self, db: Session, outlier_engine: Optional[OutlierEngine] = None):
        self.db = db
        self.outlier_engine = outlier_engine or OutlierEngine()

    def ingest_scraped_items(self, competitor_id: str, items_data: list[dict[str, Any]]) -> list[Content]:
        """Ingests scraped posts, records historical metrics, recalculates competitor baselines, and flags outliers."""
        competitor = self.db.query(Competitor).filter(Competitor.id == competitor_id).first()
        if not competitor:
            raise ValueError(f"Competitor {competitor_id} not found")

        now = datetime.now(timezone.utc)
        saved_contents = []

        for data in items_data:
            shortcode = data["shortcode"]
            content = self.db.query(Content).filter(Content.shortcode == shortcode).first()

            if not content:
                # Detect whether the Reel is new or previously known
                content = Content(
                    competitor_id=competitor.id,
                    instagram_username=data["instagram_username"],
                    instagram_profile_id=data.get("instagram_profile_id"),
                    post_id=data.get("post_id"),
                    shortcode=shortcode,
                    instagram_url=data["instagram_url"],
                    content_type=data.get("content_type", "reel"),
                    published_at=data["published_at"],
                    caption=data.get("caption"),
                    hashtags=data.get("hashtags"),
                    mentions=data.get("mentions"),
                    thumbnail_url=data.get("thumbnail_url"),
                    video_url=data.get("video_url"),
                    video_duration=data.get("video_duration"),
                    view_count=data.get("view_count"),
                    like_count=data.get("like_count"),
                    comment_count=data.get("comment_count"),
                    share_count=data.get("share_count"),
                    save_count=data.get("save_count"),
                    first_discovered_at=now,
                    last_scraped_at=now,
                )
                self.db.add(content)
                self.db.flush()
            else:
                # Update existing metric values on subsequent scans
                content.last_scraped_at = now
                if data.get("view_count") is not None:
                    content.view_count = data["view_count"]
                if data.get("like_count") is not None:
                    content.like_count = data["like_count"]
                if data.get("comment_count") is not None:
                    content.comment_count = data["comment_count"]
                if data.get("share_count") is not None:
                    content.share_count = data["share_count"]
                if data.get("save_count") is not None:
                    content.save_count = data["save_count"]
                if data.get("video_url") is not None:
                    content.video_url = data["video_url"]
                if data.get("thumbnail_url") is not None:
                    content.thumbnail_url = data["thumbnail_url"]

            # Store historical metric snapshot with delta-gating to prevent redundant database bloat
            last_metric = self.db.query(ContentMetric).filter(
                ContentMetric.content_id == content.id
            ).order_by(ContentMetric.recorded_at.desc()).first()

            view_growth = None
            velocity = None
            should_record_snapshot = False

            if last_metric is None:
                should_record_snapshot = True
            else:
                last_rec = (
                    last_metric.recorded_at.replace(tzinfo=timezone.utc)
                    if last_metric.recorded_at.tzinfo is None
                    else last_metric.recorded_at
                )
                hours_since_last = max((now - last_rec).total_seconds() / 3600.0, 0.0)

                if last_metric.views is not None and content.view_count is not None:
                    view_growth = content.view_count - last_metric.views
                    time_diff_hours = max(hours_since_last, 0.1)
                    velocity = round(view_growth / time_diff_hours, 2)

                    base_views = max(last_metric.views or 1, 1)
                    percent_change = (abs(view_growth) / base_views) * 100.0
                    if percent_change >= settings.METRIC_SNAPSHOT_MIN_DELTA_PERCENT or view_growth != 0:
                        should_record_snapshot = True

                # Also record if engagement numbers changed
                if not should_record_snapshot:
                    if (
                        content.like_count != last_metric.likes
                        or content.comment_count != last_metric.comments
                        or content.share_count != last_metric.shares
                        or content.save_count != last_metric.saves
                    ):
                        should_record_snapshot = True

                # Record cadence snapshot if maximum retention interval has elapsed
                if not should_record_snapshot and hours_since_last >= settings.METRIC_SNAPSHOT_MAX_AGE_HOURS:
                    should_record_snapshot = True

            if should_record_snapshot:
                metric_snapshot = ContentMetric(
                    content_id=content.id,
                    recorded_at=now,
                    views=content.view_count,
                    likes=content.like_count,
                    comments=content.comment_count,
                    shares=content.share_count,
                    saves=content.save_count,
                    view_growth=view_growth,
                    view_velocity=velocity,
                )
                self.db.add(metric_snapshot)
            saved_contents.append(content)

        self.db.commit()

        # Recalculate competitor baseline using recent window (prevents unbounded O(N) memory & compute)
        recent_limit = settings.BASELINE_RECENT_POSTS_LIMIT
        recent_competitor_contents = (
            self.db.query(Content)
            .filter(Content.competitor_id == competitor.id)
            .order_by(Content.published_at.desc())
            .limit(recent_limit)
            .all()
        )
        base_views, base_eng = self.outlier_engine.compute_competitor_baseline(recent_competitor_contents)
        competitor.baseline_views_median = base_views
        competitor.baseline_engagement_rate = base_eng
        competitor.last_scraped_at = now
        competitor.scrape_error = None
        self.db.commit()

        # Re-evaluate outlier scores for active batch and recent window
        items_to_evaluate = {c.id: c for c in (saved_contents + recent_competitor_contents)}.values()
        for item in items_to_evaluate:
            eval_res = self.outlier_engine.evaluate_content(item, competitor)
            was_outlier = item.is_outlier
            item.is_outlier = eval_res["is_outlier"]
            item.outlier_score = eval_res["outlier_score"]
            item.view_multiplier = eval_res["view_multiplier"]
            item.engagement_rate = eval_res["engagement_rate"]
            item.view_velocity = eval_res["view_velocity"]
            item.outlier_reasons = eval_res["outlier_reasons"]

            # Outlier media download and transcription queuing based on configuration
            if item.is_outlier and not was_outlier:
                # Video download: only queue if explicitly enabled in background settings
                if settings.AUTO_DOWNLOAD_OUTLIERS and item.download_status == "not_required":
                    item.download_status = "pending"
                    dl_job = ProcessingJob(
                        job_type="video_download",
                        status="queued",
                        content_id=item.id,
                        scheduled_at=now,
                    )
                    self.db.add(dl_job)

                # Transcription: only queue if background auto-transcription is explicitly enabled and not in on_demand mode
                should_auto_transcribe = (
                    settings.AUTO_TRANSCRIBE_OUTLIERS
                    and settings.TRANSCRIPTION_MODE != "on_demand"
                    and (
                        settings.TRANSCRIPTION_MODE == "all"
                        or (
                            settings.TRANSCRIPTION_MODE == "top_tier"
                            and item.outlier_score is not None
                            and item.outlier_score >= settings.AUTO_TRANSCRIBE_MIN_SCORE
                        )
                    )
                )

                if should_auto_transcribe and item.transcription_status == "not_required":
                    item.transcription_status = "pending"
                    tr_job = ProcessingJob(
                        job_type="transcription",
                        status="queued",
                        content_id=item.id,
                        scheduled_at=now,
                    )
                    self.db.add(tr_job)

        self.db.commit()
        return saved_contents

    def recalculate_competitor_intelligence(self, competitor_id: str) -> None:
        """Recalculates median baseline and updates view velocities, multipliers, and outlier ratings for an existing competitor."""
        competitor = self.db.query(Competitor).filter(Competitor.id == competitor_id).first()
        if not competitor:
            return

        now = datetime.now(timezone.utc)
        recent_limit = settings.BASELINE_RECENT_POSTS_LIMIT
        recent_contents = (
            self.db.query(Content)
            .filter(Content.competitor_id == competitor.id)
            .order_by(Content.published_at.desc())
            .limit(recent_limit)
            .all()
        )
        if not recent_contents:
            return

        base_views, base_eng = self.outlier_engine.compute_competitor_baseline(recent_contents)
        competitor.baseline_views_median = base_views
        competitor.baseline_engagement_rate = base_eng
        competitor.last_scraped_at = now
        competitor.scrape_error = None

        for item in recent_contents:
            eval_res = self.outlier_engine.evaluate_content(item, competitor)
            item.is_outlier = eval_res["is_outlier"]
            item.outlier_score = eval_res["outlier_score"]
            item.view_multiplier = eval_res["view_multiplier"]
            item.engagement_rate = eval_res["engagement_rate"]
            item.view_velocity = eval_res["view_velocity"]
            item.outlier_reasons = eval_res["outlier_reasons"]

        self.db.commit()

    def get_outliers(self,
                     competitor: Optional[str] = None,
                     date_range: Optional[str] = "30d",
                     min_score: float = 3.0,
                     sort: str = "score",
                     page: int = 1,
                     limit: int = 20) -> OutlierListResponse:
        """Retrieves and paginates outlier content items with filtering and sorting."""
        query = self.db.query(Content, Competitor).join(Competitor, Content.competitor_id == Competitor.id)
        query = query.filter(Content.is_outlier == True)

        if min_score:
            query = query.filter(Content.outlier_score >= min_score)

        if competitor:
            clean_comp = competitor.strip().lstrip("@").lower()
            query = query.filter((Competitor.username == clean_comp) | (Competitor.id == competitor))

        if date_range and date_range != "all":
            now = datetime.now(timezone.utc)
            days = 30
            if date_range == "7d":
                days = 7
            elif date_range == "14d":
                days = 14
            elif date_range == "30d":
                days = 30
            elif date_range == "60d":
                days = 60
            elif date_range == "90d":
                days = 90
            elif date_range.endswith("d") and date_range[:-1].isdigit():
                days = int(date_range[:-1])
            cutoff = now - timedelta(days=days)
            query = query.filter(Content.published_at >= cutoff)

        if sort == "views":
            query = query.order_by(desc(Content.view_count))
        elif sort == "velocity":
            query = query.order_by(desc(Content.view_velocity))
        elif sort == "published":
            query = query.order_by(desc(Content.published_at))
        else:  # default 'score'
            query = query.order_by(desc(Content.outlier_score))

        total = query.count()
        offset = (page - 1) * limit
        rows = query.offset(offset).limit(limit).all()

        items = []
        now = datetime.now(timezone.utc)
        for content, comp in rows:
            pub = content.published_at
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            age_days = max(int((now - pub).total_seconds() / 86400.0), 0)

            items.append(OutlierCardResponse(
                id=content.id,
                shortcode=content.shortcode,
                instagram_url=content.instagram_url,
                username=comp.username,
                caption=content.caption,
                thumbnail_url=content.thumbnail_url,
                video_url=content.video_url,
                view_count=content.view_count,
                like_count=content.like_count,
                comment_count=content.comment_count,
                published_at=content.published_at,
                age_days=age_days,
                outlier_score=content.outlier_score,
                view_multiplier=content.view_multiplier,
                baseline_views=int(comp.baseline_views_median) if comp.baseline_views_median else None,
                engagement_rate=content.engagement_rate,
                view_velocity=content.view_velocity,
                outlier_reasons=content.outlier_reasons,
                download_status=content.download_status,
                transcription_status=content.transcription_status,
            ))

        return OutlierListResponse(items=items, total=total, page=page, limit=limit)

    def get_dashboard_data(self) -> DashboardResponse:
        """Returns aggregate overview data matching the frontend dashboard metrics & hero card."""
        competitors_count = self.db.query(func.count(Competitor.id)).scalar() or 0
        content_tracked_count = self.db.query(func.count(Content.id)).scalar() or 0
        outliers_found_count = self.db.query(func.count(Content.id)).filter(Content.is_outlier == True).scalar() or 0

        latest_scrape = self.db.query(func.max(Competitor.last_scraped_at)).scalar()
        last_updated_human = "Never"
        if latest_scrape:
            now = datetime.now(timezone.utc)
            if latest_scrape.tzinfo is None:
                latest_scrape = latest_scrape.replace(tzinfo=timezone.utc)
            diff_hours = int((now - latest_scrape).total_seconds() / 3600.0)
            if diff_hours == 0:
                mins = int((now - latest_scrape).total_seconds() / 60.0)
                last_updated_human = f"{max(mins, 1)}m ago"
            else:
                last_updated_human = f"{diff_hours}h ago"

        outliers_resp = self.get_outliers(limit=4, sort="score")
        top_outlier = outliers_resp.items[0] if outliers_resp.items else None
        recent_outliers = outliers_resp.items[1:] if len(outliers_resp.items) > 1 else []

        return DashboardResponse(
            competitors_count=competitors_count,
            content_tracked_count=content_tracked_count,
            outliers_found_count=outliers_found_count,
            last_updated=latest_scrape,
            last_updated_human=last_updated_human,
            top_outlier=top_outlier,
            recent_outliers=recent_outliers,
        )

    def get_content_by_id(self, content_id: str) -> Optional[Content]:
        return self.db.query(Content).filter(Content.id == content_id).first()

    def get_metrics_history(self, content_id: str) -> list[ContentMetric]:
        return self.db.query(ContentMetric).filter(
            ContentMetric.content_id == content_id
        ).order_by(ContentMetric.recorded_at.asc()).all()

    def get_transcript(self, content_id: str) -> Optional[Transcript]:
        return self.db.query(Transcript).filter(Transcript.content_id == content_id).first()
