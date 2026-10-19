"""001_initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-24 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False, unique=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('hashed_password', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # 2. competitors
    op.create_table(
        'competitors',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('username', sa.String(length=100), nullable=False, unique=True),
        sa.Column('instagram_id', sa.String(length=100), nullable=True),
        sa.Column('profile_name', sa.String(length=255), nullable=True),
        sa.Column('profile_image', sa.String(length=1024), nullable=True),
        sa.Column('followers', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, default='active'),
        sa.Column('last_scraped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scrape_error', sa.Text(), nullable=True),
        sa.Column('rate_limited_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('baseline_views_median', sa.Float(), nullable=True),
        sa.Column('baseline_engagement_rate', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_competitors_username', 'competitors', ['username'])

    # 3. content
    op.create_table(
        'content',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('competitor_id', sa.String(length=36), sa.ForeignKey('competitors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('instagram_username', sa.String(length=100), nullable=False),
        sa.Column('instagram_profile_id', sa.String(length=100), nullable=True),
        sa.Column('post_id', sa.String(length=100), nullable=True),
        sa.Column('shortcode', sa.String(length=100), nullable=False, unique=True),
        sa.Column('instagram_url', sa.String(length=500), nullable=False),
        sa.Column('content_type', sa.String(length=50), nullable=False, default='reel'),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('hashtags', sa.JSON(), nullable=True),
        sa.Column('mentions', sa.JSON(), nullable=True),
        sa.Column('thumbnail_url', sa.String(length=1024), nullable=True),
        sa.Column('thumbnail_path', sa.String(length=500), nullable=True),
        sa.Column('video_url', sa.String(length=1024), nullable=True),
        sa.Column('video_path', sa.String(length=500), nullable=True),
        sa.Column('video_duration', sa.Float(), nullable=True),
        sa.Column('view_count', sa.BigInteger(), nullable=True),
        sa.Column('like_count', sa.Integer(), nullable=True),
        sa.Column('comment_count', sa.Integer(), nullable=True),
        sa.Column('share_count', sa.Integer(), nullable=True),
        sa.Column('save_count', sa.Integer(), nullable=True),
        sa.Column('first_discovered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_scraped_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_outlier', sa.Boolean(), nullable=False, default=False),
        sa.Column('outlier_score', sa.Float(), nullable=False, default=1.0),
        sa.Column('view_multiplier', sa.Float(), nullable=True),
        sa.Column('engagement_rate', sa.Float(), nullable=True),
        sa.Column('view_velocity', sa.Float(), nullable=True),
        sa.Column('outlier_reasons', sa.JSON(), nullable=True),
        sa.Column('download_status', sa.String(length=50), nullable=False, default='not_required'),
        sa.Column('transcription_status', sa.String(length=50), nullable=False, default='not_required'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_content_shortcode', 'content', ['shortcode'])
    op.create_index('ix_content_competitor_id', 'content', ['competitor_id'])
    op.create_index('ix_content_is_outlier', 'content', ['is_outlier'])
    op.create_index('ix_content_published_at', 'content', ['published_at'])
    op.create_index('ix_content_outlier_score', 'content', ['is_outlier', 'outlier_score'])
    op.create_index('ix_content_competitor_published', 'content', ['competitor_id', 'published_at'])

    # 4. content_metrics
    op.create_table(
        'content_metrics',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('content_id', sa.String(length=36), sa.ForeignKey('content.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('views', sa.BigInteger(), nullable=True),
        sa.Column('likes', sa.Integer(), nullable=True),
        sa.Column('comments', sa.Integer(), nullable=True),
        sa.Column('shares', sa.Integer(), nullable=True),
        sa.Column('saves', sa.Integer(), nullable=True),
        sa.Column('view_growth', sa.BigInteger(), nullable=True),
        sa.Column('view_velocity', sa.Float(), nullable=True),
        sa.Column('engagement_rate', sa.Float(), nullable=True),
    )
    op.create_index('ix_content_metrics_content_id', 'content_metrics', ['content_id'])
    op.create_index('ix_content_metrics_recorded_at', 'content_metrics', ['recorded_at'])
    op.create_index('ix_content_metrics_content_time', 'content_metrics', ['content_id', 'recorded_at'])

    # 5. transcripts
    op.create_table(
        'transcripts',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('content_id', sa.String(length=36), sa.ForeignKey('content.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('full_text', sa.Text(), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False, default='en'),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('segments', sa.JSON(), nullable=True),
        sa.Column('hook_text', sa.Text(), nullable=True),
        sa.Column('breakdown_hook', sa.Text(), nullable=True),
        sa.Column('breakdown_topic', sa.Text(), nullable=True),
        sa.Column('breakdown_format', sa.Text(), nullable=True),
        sa.Column('breakdown_cta', sa.Text(), nullable=True),
        sa.Column('key_takeaways', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_transcripts_content_id', 'transcripts', ['content_id'])

    # 6. scrape_jobs
    op.create_table(
        'scrape_jobs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, default='queued'),
        sa.Column('competitor_id', sa.String(length=36), sa.ForeignKey('competitors.id', ondelete='CASCADE'), nullable=True),
        sa.Column('content_id', sa.String(length=36), sa.ForeignKey('content.id', ondelete='CASCADE'), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, default=0),
        sa.Column('max_attempts', sa.Integer(), nullable=False, default=3),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_scrape_jobs_status', 'scrape_jobs', ['status'])
    op.create_index('ix_scrape_jobs_competitor_id', 'scrape_jobs', ['competitor_id'])
    op.create_index('ix_scrape_jobs_status_sched', 'scrape_jobs', ['status', 'scheduled_at'])

    # 7. processing_jobs
    op.create_table(
        'processing_jobs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, default='queued'),
        sa.Column('content_id', sa.String(length=36), sa.ForeignKey('content.id', ondelete='CASCADE'), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, default=0),
        sa.Column('max_attempts', sa.Integer(), nullable=False, default=3),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_processing_jobs_status', 'processing_jobs', ['status'])
    op.create_index('ix_processing_jobs_content_id', 'processing_jobs', ['content_id'])
    op.create_index('ix_processing_jobs_status_sched', 'processing_jobs', ['status', 'scheduled_at'])


def downgrade() -> None:
    op.drop_table('processing_jobs')
    op.drop_table('scrape_jobs')
    op.drop_table('transcripts')
    op.drop_table('content_metrics')
    op.drop_table('content')
    op.drop_table('competitors')
    op.drop_table('users')
