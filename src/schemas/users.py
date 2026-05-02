"""Pydantic schemas for the user / auth API.

These models bracket every HTTP boundary in the auth subsystem: they
define what the API accepts (input schemas — ``UserCreate``,
``RefreshTokenRequest``, ``ResetPasswordConfirm``, ``RequestEmail``,
``UserRoleUpdate``) and what it returns (output schemas —
``UserResponse``, ``TokenResponse``).

Pydantic v2 ``ConfigDict(from_attributes=True)`` lets the response
schemas hydrate directly from SQLAlchemy ORM rows.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.database.models import UserRole


class UserCreate(BaseModel):
    """Payload for ``POST /api/auth/register``.

    All three fields are required. Validation:

    * ``username`` — 2..50 characters.
    * ``email`` — RFC-validated email.
    * ``password`` — 6..128 characters (the upper bound stops bcrypt
      from silently truncating very long inputs).
    """

    username: str = Field(min_length=2, max_length=50, examples=["ivan"])
    email: EmailStr = Field(examples=["ivan@example.com"])
    password: str = Field(min_length=6, max_length=128, examples=["str0ngP@ss"])


class UserResponse(BaseModel):
    """Public representation of a :class:`~src.database.models.User`.

    Includes ``role`` so the client can adjust the UI for admins.
    Sensitive fields like ``hashed_password`` are intentionally absent.
    """

    id: int
    username: str
    email: EmailStr
    avatar: Optional[str] = None
    confirmed: bool
    role: UserRole
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """OAuth2-compatible token pair returned by ``/login`` and ``/refresh``."""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Payload for ``POST /api/auth/refresh``."""

    refresh_token: str


class RequestEmail(BaseModel):
    """Payload that carries an email address.

    Used by the resend-verification and password-reset request endpoints.
    """

    email: EmailStr


class ResetPasswordConfirm(BaseModel):
    """Payload for ``POST /api/auth/reset-password/confirm``.

    The token is single-use — see
    :func:`~src.api.auth.confirm_password_reset`.
    """

    token: str
    new_password: str = Field(min_length=6, max_length=128)


class UserRoleUpdate(BaseModel):
    """Payload for the admin-only role update endpoint."""

    role: UserRole
