import statistics
from datetime import datetime, timezone
from typing import Optional, Any
from app.config import settings
from app.models.content import Content
from app.models.competitor import Competitor


class OutlierEngine:
    """Core intelligence service for calculating baselines, multipliers, velocities, and explainable outlier scores."""

    def __init__(self,
                 view_weight: float = settings.OUTLIER_VIEW_MULTIPLIER_WEIGHT,
                 engagement_weight: float = settings.OUTLIER_ENGAGEMENT_WEIGHT,
                 velocity_weight: float = settings.OUTLIER_VELOCITY_WEIGHT,
                 threshold_multiplier: float = settings.OUTLIER_THRESHOLD_MULTIPLIER):
        self.view_weight = view_weight
        self.engagement_weight = engagement_weight
        self.velocity_weight = velocity_weight
        self.threshold_multiplier = threshold_multiplier

    def compute_competitor_baseline(self, competitor_contents: list[Content]) -> tuple[Optional[float], Optional[float]]:
        """Calculates robust historical median baseline views and median engagement rate for a competitor."""
        valid_views = [c.view_count for c in competitor_contents if c.view_count is not None and c.view_count > 0]
        baseline_views = float(statistics.median(valid_views)) if len(valid_views) >= settings.OUTLIER_MIN_BASELINE_POSTS else None

        valid_engagements = []
        for c in competitor_contents:
            if c.view_count and c.view_count > 0 and (c.like_count is not None or c.comment_count is not None):
                likes = c.like_count or 0
                comments = c.comment_count or 0
                valid_engagements.append((likes + comments) / c.view_count)

        baseline_eng = float(statistics.median(valid_engagements)) if len(valid_engagements) >= settings.OUTLIER_MIN_BASELINE_POSTS else None

        return baseline_views, baseline_eng

    def evaluate_content(self, content: Content, competitor: Competitor) -> dict[str, Any]:
        """Calculates metrics, velocity, multiplier, composite score, and structured explainability for a Reel."""
        now = datetime.now(timezone.utc)
        published = content.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)

        age_seconds = max((now - published).total_seconds(), 3600.0)
        age_hours = age_seconds / 3600.0
        age_days = int(age_seconds / 86400.0)

        # 1. View velocity (views per hour)
        view_velocity = None
        if content.view_count is not None and content.view_count > 0:
            view_velocity = round(content.view_count / age_hours, 2)

        # 2. Engagement rate
        engagement_rate = None
        if content.view_count is not None and content.view_count > 0:
            likes = content.like_count or 0
            comments = content.comment_count or 0
            engagement_rate = round((likes + comments) / content.view_count, 4)
        elif competitor.followers and competitor.followers > 0 and (content.like_count or content.comment_count):
            likes = content.like_count or 0
            comments = content.comment_count or 0
            engagement_rate = round((likes + comments) / competitor.followers, 4)

        # 3. View multiplier against account median baseline
        view_multiplier = None
        baseline_views = competitor.baseline_views_median
        if content.view_count is not None and baseline_views and baseline_views > 0:
            view_multiplier = round(content.view_count / baseline_views, 2)

        # 4. Engagement lift relative to baseline
        engagement_lift = 1.0
        if engagement_rate and competitor.baseline_engagement_rate and competitor.baseline_engagement_rate > 0:
            engagement_lift = round(engagement_rate / competitor.baseline_engagement_rate, 2)

        # 5. Outlier scoring, recency weighting, and classification
        is_outlier = False
        outlier_score = 1.0

        # Recency weighting: newer content (under 30-45 days) with strong momentum
        # receives higher weight than older, plateaued posts.
        recency_weight = max(1.0, round(1.6 - (age_days / 50.0), 2)) if age_days <= 60 else 1.0

        if view_multiplier is not None:
            # Velocity factor: normalized bonus for fast-growing content
            velocity_factor = min(max((view_velocity or 0) / 1000.0, 0.5), 3.0)
            
            # Base composite combining view multiplier, engagement lift, and velocity
            composite = (view_multiplier * self.view_weight) + (view_multiplier * (engagement_lift - 1.0) * self.engagement_weight) + (velocity_factor * self.velocity_weight)
            raw_score = max(round(view_multiplier, 1), round(composite, 1))

            # Apply recency weighting
            outlier_score = round(raw_score * recency_weight, 1)

            if view_multiplier >= self.threshold_multiplier or outlier_score >= self.threshold_multiplier:
                is_outlier = True
        elif engagement_rate and engagement_rate > 0.10:
            # High engagement fallback when views are missing/hidden
            raw_score = round(engagement_rate * 20.0, 1)
            outlier_score = round(raw_score * recency_weight, 1)
            if outlier_score >= self.threshold_multiplier:
                is_outlier = True

        # 6. Structured explainability reasons
        explanation_text = self._build_explanation_summary(
            username=competitor.username,
            view_multiplier=view_multiplier,
            view_count=content.view_count,
            baseline_views=baseline_views,
            engagement_rate=engagement_rate,
            engagement_lift=engagement_lift,
            view_velocity=view_velocity,
            age_days=age_days,
            is_outlier=is_outlier,
        )

        reasons = {
            "view_multiplier": view_multiplier,
            "account_baseline_views": int(baseline_views) if baseline_views else None,
            "account_baseline_engagement": competitor.baseline_engagement_rate,
            "engagement_rate": engagement_rate,
            "engagement_lift": engagement_lift,
            "view_velocity_hourly": view_velocity,
            "age_days": age_days,
            "recency_weight": recency_weight,
            "summary": explanation_text,
        }

        return {
            "is_outlier": is_outlier,
            "outlier_score": outlier_score,
            "view_multiplier": view_multiplier,
            "engagement_rate": engagement_rate,
            "view_velocity": view_velocity,
            "outlier_reasons": reasons,
        }

    def _build_explanation_summary(self, username: str, view_multiplier: Optional[float],
                                   view_count: Optional[int], baseline_views: Optional[float],
                                   engagement_rate: Optional[float], engagement_lift: float,
                                   view_velocity: Optional[float], age_days: int, is_outlier: bool) -> str:
        """Constructs human-readable rationale for why content succeeded or deviated."""
        if not is_outlier or not view_multiplier:
            return f"Performing within expected baseline for @{username}."

        parts = [f"Generated {view_multiplier}× more views than @{username}'s normal baseline ({int(baseline_views):,} views)"]
        if engagement_lift > 1.2:
            parts.append(f"with {int((engagement_lift - 1.0) * 100)}% higher audience engagement")
        if view_velocity and view_velocity > 500:
            parts.append(f"driving {int(view_velocity):,} views/hour over {age_days} days")

        return "; ".join(parts) + "."
