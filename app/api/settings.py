from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.setting import (
    InstagramCredentialsInput,
    InstagramSessionCookieInput,
    InstagramStatusResponse,
    InstagramConnectResponse,
)
from app.services.instagram_auth_service import InstagramAuthService


router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/instagram", response_model=InstagramStatusResponse)
def get_instagram_status(db: Session = Depends(get_db)):
    """Returns current Instagram scraping account connection and session health."""
    return InstagramAuthService.get_status(db)


@router.post("/instagram", response_model=InstagramConnectResponse)
def connect_instagram(data: InstagramCredentialsInput, db: Session = Depends(get_db)):
    """Authenticates with Instagram, creates a fresh session, and saves credentials for auto-renewal."""
    success, message = InstagramAuthService.login_and_save(data.username, data.password, db)
    status_info = InstagramAuthService.get_status(db)
    if not success:
        return InstagramConnectResponse(
            success=False,
            message=message,
            status=status_info["status"],
            username=data.username,
        )
    return InstagramConnectResponse(
        success=True,
        message=message,
        status="connected",
        username=data.username,
    )


@router.post("/instagram/session", response_model=InstagramConnectResponse)
def connect_instagram_session(data: InstagramSessionCookieInput, db: Session = Depends(get_db)):
    """Connects instantly using an Instagram session cookie (bypasses checkpoint challenges)."""
    success, message = InstagramAuthService.save_session_cookie(
        data.username, data.session_id, data.ds_user_id, db
    )
    status_info = InstagramAuthService.get_status(db)
    return InstagramConnectResponse(
        success=success,
        message=message,
        status=status_info["status"],
        username=data.username,
    )



@router.post("/instagram/renew", response_model=InstagramConnectResponse)
def renew_instagram_session(db: Session = Depends(get_db)):
    """Manually forces an automatic session renewal using stored credentials."""
    success, message = InstagramAuthService.auto_renew(db)
    status_info = InstagramAuthService.get_status(db)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )
    return InstagramConnectResponse(
        success=True,
        message=message,
        status=status_info["status"],
        username=status_info["username"],
    )


@router.delete("/instagram", response_model=dict)
def disconnect_instagram(db: Session = Depends(get_db)):
    """Removes stored Instagram credentials and deletes active session."""
    InstagramAuthService.disconnect(db)
    return {"message": "Instagram account disconnected."}


@router.get("/instagram/credentials", response_model=dict)
def get_instagram_credentials_for_agent(db: Session = Depends(get_db)):
    """Allows local scraping agent to obtain credentials to scrape from residential IP."""
    username, password = InstagramAuthService.get_credentials(db)
    status_info = InstagramAuthService.get_status(db)
    return {
        "username": username,
        "password": password,
        "status": status_info["status"],
        "has_session": status_info["has_session"],
    }
