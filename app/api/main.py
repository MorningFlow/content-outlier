from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.config import settings
from app.database import engine, Base, ensure_schema_columns
import app.models  # ensure models are loaded
from app.api.competitors import router as competitors_router
from app.api.outliers import router as outliers_router
from app.api.dashboard import router as dashboard_router
from app.api.content import router as content_router
from app.api.jobs import router as jobs_router
from app.api.settings import router as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database schema tables exist and dynamic columns are present
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns(engine)
    yield


app = FastAPI(
    title="Content Outlier API",
    description="Backend API and Intelligence Engine for Content Outlier Competitor Tracking",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Media Storage Static Mount
media_dir = settings.storage_path
app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

# Include API Routers
app.include_router(dashboard_router)
app.include_router(competitors_router)
app.include_router(outliers_router)
app.include_router(content_router)
app.include_router(jobs_router)
app.include_router(settings_router)



@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "env": settings.APP_ENV,
        "database": "sqlite" if settings.is_sqlite else "postgresql",
        "storage": settings.STORAGE_BACKEND,
    }


# Frontend integration: Serve content-outlier.html directly at root
html_path = Path(__file__).resolve().parent.parent.parent / "content-outlier.html"
if html_path.is_file():
    @app.get("/", include_in_schema=False)
    def serve_frontend():
        return FileResponse(str(html_path))
