-- Content Outlier PostgreSQL DDL Schema
-- Run on any PostgreSQL 14+ database

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255),
    hashed_password VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS competitors (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    instagram_id VARCHAR(100),
    profile_name VARCHAR(255),
    profile_image VARCHAR(1024),
    followers INTEGER,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    last_scraped_at TIMESTAMPTZ,
    scrape_error TEXT,
    rate_limited_until TIMESTAMPTZ,
    baseline_views_median DOUBLE PRECISION,
    baseline_engagement_rate DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_competitors_username ON competitors (username);

CREATE TABLE IF NOT EXISTS content (
    id VARCHAR(36) PRIMARY KEY,
    competitor_id VARCHAR(36) NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    instagram_username VARCHAR(100) NOT NULL,
    instagram_profile_id VARCHAR(100),
    post_id VARCHAR(100),
    shortcode VARCHAR(100) NOT NULL UNIQUE,
    instagram_url VARCHAR(500) NOT NULL,
    content_type VARCHAR(50) NOT NULL DEFAULT 'reel',
    published_at TIMESTAMPTZ NOT NULL,
    caption TEXT,
    hashtags JSONB,
    mentions JSONB,
    thumbnail_url VARCHAR(1024),
    thumbnail_path VARCHAR(500),
    video_url VARCHAR(1024),
    video_path VARCHAR(500),
    video_duration DOUBLE PRECISION,
    view_count BIGINT,
    like_count INTEGER,
    comment_count INTEGER,
    share_count INTEGER,
    save_count INTEGER,
    first_discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_outlier BOOLEAN NOT NULL DEFAULT FALSE,
    outlier_score DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    view_multiplier DOUBLE PRECISION,
    engagement_rate DOUBLE PRECISION,
    view_velocity DOUBLE PRECISION,
    outlier_reasons JSONB,
    download_status VARCHAR(50) NOT NULL DEFAULT 'not_required',
    transcription_status VARCHAR(50) NOT NULL DEFAULT 'not_required',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_content_shortcode ON content (shortcode);
CREATE INDEX IF NOT EXISTS ix_content_competitor_id ON content (competitor_id);
CREATE INDEX IF NOT EXISTS ix_content_is_outlier ON content (is_outlier);
CREATE INDEX IF NOT EXISTS ix_content_published_at ON content (published_at);
CREATE INDEX IF NOT EXISTS ix_content_outlier_score ON content (is_outlier, outlier_score DESC);
CREATE INDEX IF NOT EXISTS ix_content_competitor_published ON content (competitor_id, published_at DESC);

CREATE TABLE IF NOT EXISTS content_metrics (
    id VARCHAR(36) PRIMARY KEY,
    content_id VARCHAR(36) NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    views BIGINT,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    saves INTEGER,
    view_growth BIGINT,
    view_velocity DOUBLE PRECISION,
    engagement_rate DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS ix_content_metrics_content_id ON content_metrics (content_id);
CREATE INDEX IF NOT EXISTS ix_content_metrics_recorded_at ON content_metrics (recorded_at);
CREATE INDEX IF NOT EXISTS ix_content_metrics_content_time ON content_metrics (content_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS transcripts (
    id VARCHAR(36) PRIMARY KEY,
    content_id VARCHAR(36) NOT NULL UNIQUE REFERENCES content(id) ON DELETE CASCADE,
    full_text TEXT NOT NULL,
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    duration DOUBLE PRECISION,
    segments JSONB,
    hook_text TEXT,
    breakdown_hook TEXT,
    breakdown_topic TEXT,
    breakdown_format TEXT,
    breakdown_cta TEXT,
    key_takeaways TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_transcripts_content_id ON transcripts (content_id);

CREATE TABLE IF NOT EXISTS scrape_jobs (
    id VARCHAR(36) PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    competitor_id VARCHAR(36) REFERENCES competitors(id) ON DELETE CASCADE,
    content_id VARCHAR(36) REFERENCES content(id) ON DELETE CASCADE,
    payload JSONB,
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_scrape_jobs_status_sched ON scrape_jobs (status, scheduled_at);
CREATE INDEX IF NOT EXISTS ix_scrape_jobs_competitor_id ON scrape_jobs (competitor_id);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id VARCHAR(36) PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    content_id VARCHAR(36) NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    payload JSONB,
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_processing_jobs_status_sched ON processing_jobs (status, scheduled_at);
CREATE INDEX IF NOT EXISTS ix_processing_jobs_content_id ON processing_jobs (content_id);
