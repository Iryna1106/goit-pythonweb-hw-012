"""Pydantic schemas for the user / auth API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.database.models import UserRole


class UserCreate(BaseModel):
    """Payload for ``POST /api/auth/register``."""

    username: str = Field(min_length=2, max_length=50, examples=["ivan"])
    email: EmailStr = Field(examples=["ivan@example.com"])
    password: str = Field(min_length=6, max_length=128, examples=["str0ngP@ss"])


class UserResponse(BaseModel):
    """Public representation of a :class:`~src.database.models.User`."""

    id: int
    username: str
    email: EmailStr
    avatar: Optional[str] = None
    confirmed: bool
    role: UserRole
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """OAuth2-compatible access + refresh token pair."""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Payload for ``POST /api/auth/refresh``."""

    refresh_token: str


class RequestEmail(BaseModel):
    """Payload that carries an email address (used by request-email and password-reset endpoints)."""

    email: EmailStr


class ResetPasswordConfirm(BaseModel):
    """Payload for ``POST /api/auth/reset-password/confirm``."""

    token: str
    new_password: str = Field(min_length=6, max_length=128)
