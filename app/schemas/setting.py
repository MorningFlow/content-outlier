from typing import Optional
from pydantic import BaseModel, Field


class InstagramCredentialsInput(BaseModel):
    username: str = Field(..., description="Instagram username (with or without @)")
    password: str = Field(..., description="Instagram account password")


class InstagramSessionCookieInput(BaseModel):
    username: str = Field(..., description="Instagram username")
    session_id: str = Field(..., description="Instagram sessionid cookie value")
    ds_user_id: Optional[str] = Field(None, description="Optional ds_user_id cookie value")



class InstagramStatusResponse(BaseModel):
    configured: bool
    username: Optional[str] = None
    status: str
    has_session: bool
    last_authenticated: Optional[str] = None
    error_message: Optional[str] = None


class InstagramConnectResponse(BaseModel):
    success: bool
    message: str
    status: str
    username: Optional[str] = None
