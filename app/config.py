from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Application
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    SECRET_KEY: str = "content-outlier-dev-secret-key-32chars-min"

    # Database
    DATABASE_URL: str = "sqlite:///./content_outlier.db"

    # Storage
    STORAGE_BACKEND: str = "local"  # "local" or "s3"
    LOCAL_STORAGE_DIR: str = "./media_storage"
    
    # S3 / Cloudflare R2
    S3_ENDPOINT_URL: Optional[str] = None
    S3_BUCKET_NAME: str = "content-outlier-media"
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_REGION_NAME: str = "auto"
    S3_PUBLIC_BASE_URL: Optional[str] = None

    # Instagram Scraper
    INSTAGRAM_USERNAME: Optional[str] = None
    INSTAGRAM_PASSWORD: Optional[str] = None
    INSTAGRAM_SESSION_FILE: Optional[str] = None
    INSTAGRAM_SESSION_ID: Optional[str] = None
    INSTAGRAM_DS_USER_ID: Optional[str] = None
    INSTAGRAM_CSRF_TOKEN: Optional[str] = None
    MAX_REELS_PER_SCRAPE: int = 50
    SCRAPE_DAYS_CUTOFF: int = 30
    SCRAPE_DELAY_SECONDS: float = 3.5
    RATE_LIMIT_BACKOFF_MINUTES: int = 60
    # Proxy for all Instagram scraping requests (e.g. http://user:pass@host:port or socks5://host:port)
    SCRAPING_PROXY: Optional[str] = None
    # When True the background scheduler does not auto-queue scrapes;
    # scraping only happens when triggered via the API (on platform open).
    ON_DEMAND_ONLY: bool = True

    # Outlier Intelligence
    OUTLIER_MIN_BASELINE_POSTS: int = 3
    OUTLIER_VIEW_MULTIPLIER_WEIGHT: float = 0.60
    OUTLIER_ENGAGEMENT_WEIGHT: float = 0.25
    OUTLIER_VELOCITY_WEIGHT: float = 0.15
    OUTLIER_THRESHOLD_MULTIPLIER: float = 3.0

    # Worker & Transcription Settings
    WORKER_CONCURRENCY: int = 2
    WORKER_POLL_INTERVAL: float = 5.0
    WORKER_MAX_POLL_INTERVAL: float = 30.0
    DEFAULT_SCAN_INTERVAL_HOURS: int = 6
    AUTO_DOWNLOAD_OUTLIERS: bool = False
    AUTO_TRANSCRIBE_OUTLIERS: bool = False
    TRANSCRIPTION_MODE: str = "on_demand"  # "on_demand", "top_tier", "all", "disabled"
    AUTO_TRANSCRIBE_MIN_SCORE: float = 5.0
    WHISPER_MODEL_SIZE: str = "tiny"
    WHISPER_BEAM_SIZE: int = 1
    WHISPER_VAD_FILTER: bool = True
    WHISPER_DEVICE: str = "auto"  # "auto", "cpu", "cuda"
    WHISPER_CPU_THREADS: int = 2
    WHISPER_IDLE_TTL_SECONDS: int = 600

    # Resource Optimization & Retention
    METRIC_SNAPSHOT_MIN_DELTA_PERCENT: float = 1.0
    METRIC_SNAPSHOT_MAX_AGE_HOURS: float = 48.0
    BASELINE_RECENT_POSTS_LIMIT: int = 50

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def storage_path(self) -> Path:
        path = Path(self.LOCAL_STORAGE_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
