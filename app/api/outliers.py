from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.content_service import ContentService
from app.schemas.outlier import OutlierListResponse

router = APIRouter(prefix="/outliers", tags=["Outliers"])


@router.get("", response_model=OutlierListResponse)
def get_outliers(
    competitor: Optional[str] = Query(None, description="Competitor username or ID"),
    range: Optional[str] = Query("30d", description="Time window: '7d', '14d', '30d', '90d', or 'all'"),
    min_score: float = Query(3.0, description="Minimum outlier multiplier score"),
    sort: str = Query("score", description="Sort by: 'score', 'views', 'velocity', or 'published'"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
):
    """Retrieve high-performing outlier Reels relative to each account's historical baseline."""
    service = ContentService(db)
    return service.get_outliers(
        competitor=competitor,
        date_range=range,
        min_score=min_score,
        sort=sort,
        page=page,
        limit=limit,
    )
