from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

connect_args = {}
if settings.is_sqlite:
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema_columns(bind_engine=engine):
    """Ensures progress columns exist on scrape_jobs and processing_jobs."""
    try:
        with bind_engine.connect() as conn:
            if settings.is_sqlite:
                for table in ["scrape_jobs", "processing_jobs"]:
                    cols = [r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()]
                    if cols and "progress_percent" not in cols:
                        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN progress_percent INTEGER DEFAULT 0")
                    if cols and "progress_stage" not in cols:
                        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN progress_stage VARCHAR(255)")
            else:
                for table in ["scrape_jobs", "processing_jobs"]:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS progress_percent INTEGER DEFAULT 0")
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS progress_stage VARCHAR(255)")
            conn.commit()
    except Exception:
        pass
