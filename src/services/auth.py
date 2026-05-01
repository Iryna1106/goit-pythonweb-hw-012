"""Authentication primitives: password hashing, JWT helpers, and FastAPI dependencies.

This module exposes:

* :func:`verify_password` / :func:`get_password_hash` — bcrypt hashing wrappers.
* :func:`create_access_token`, :func:`create_refresh_token`,
  :func:`create_email_token`, :func:`create_password_reset_token` — JWT issuers
  for the four token scopes used by the API.
* :func:`decode_token` — strict scope-checking decoder.
* :func:`get_current_user` — FastAPI dependency that resolves the authenticated
  user, transparently using a Redis cache to avoid a DB round-trip per request.
* :func:`require_admin` — dependency that 403s non-admin callers.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from src.conf.config import settings
from src.database.db import get_db
from src.database.models import User, UserRole
from src.services import cache as user_cache

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

ACCESS_TOKEN_SCOPE = "access_token"
REFRESH_TOKEN_SCOPE = "refresh_token"
EMAIL_TOKEN_SCOPE = "email_token"
RESET_PASSWORD_TOKEN_SCOPE = "reset_password_token"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return ``True`` when ``plain_password`` matches ``hashed_password``."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash ``password`` with bcrypt."""
    return pwd_context.hash(password)


def _create_token(data: dict, expires_delta: timedelta, scope: str) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    to_encode.update({"iat": now, "exp": now + expires_delta, "scope": scope})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    """Issue a short-lived access JWT carrying ``subject`` (the user's email) in ``sub``."""
    minutes = expires_minutes or settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    return _create_token({"sub": subject}, timedelta(minutes=minutes), ACCESS_TOKEN_SCOPE)


def create_refresh_token(subject: str, expires_days: Optional[int] = None) -> str:
    """Issue a refresh JWT used to mint new access tokens via ``/api/auth/refresh``."""
    days = expires_days or settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    return _create_token({"sub": subject}, timedelta(days=days), REFRESH_TOKEN_SCOPE)


def create_email_token(subject: str) -> str:
    """Issue an email-verification JWT delivered via the verification email."""
    return _create_token(
        {"sub": subject},
        timedelta(hours=settings.JWT_EMAIL_TOKEN_EXPIRE_HOURS),
        EMAIL_TOKEN_SCOPE,
    )


def create_password_reset_token(subject: str) -> str:
    """Issue a short-TTL JWT scoped for the password-reset flow."""
    return _create_token(
        {"sub": subject},
        timedelta(minutes=settings.JWT_RESET_PASSWORD_TOKEN_EXPIRE_MINUTES),
        RESET_PASSWORD_TOKEN_SCOPE,
    )


def decode_token(token: str, expected_scope: str) -> str:
    """Decode ``token`` and return its ``sub`` claim, validating signature + scope.

    :raises HTTPException: 401 on any decode/scope error.
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("scope") != expected_scope:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token scope",
            headers={"WWW-Authenticate": "Bearer"},
        )
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return sub


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency that resolves the authenticated :class:`User`.

    The user is first looked up in Redis; on miss the database is queried and
    the result cached. Callers that need an admin should depend on
    :func:`require_admin` instead.

    :raises HTTPException: 401 if the token is invalid or the user is missing.
    """
    email = decode_token(token, ACCESS_TOKEN_SCOPE)

    cached = user_cache.get_cached_user(email)
    if cached is not None:
        return cached

    # Avoid circular import: import lazily.
    from src.repository import users as repo_users

    user = repo_users.get_user_by_email(db, email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_cache.cache_user(user)
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency that 403s any caller whose role is not ``admin``."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
