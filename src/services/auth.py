"""Authentication primitives for the Contacts REST API.

This module is the security backbone of the application. It exposes:

* **Password hashing** — bcrypt via :mod:`passlib`.
* **JWT issuing / decoding** — four scoped token types so that an access token
  cannot be used as a refresh token, an email-confirmation token cannot be
  used to reset a password, etc.
* **FastAPI dependencies** — :func:`get_current_user` resolves the
  authenticated user (transparently using a Redis cache so we do not
  round-trip the database on every request) and :func:`require_admin`
  enforces role-based access for administrator-only endpoints.

Token scopes
------------

Each JWT carries a custom ``scope`` claim that callers must verify with
:func:`decode_token`. The four scopes used by the API:

================================  =====================================  ======================================
Scope constant                    Issued by                              Used by
================================  =====================================  ======================================
``ACCESS_TOKEN_SCOPE``            :func:`create_access_token`            Bearer auth
``REFRESH_TOKEN_SCOPE``           :func:`create_refresh_token`           ``POST /auth/refresh``
``EMAIL_TOKEN_SCOPE``             :func:`create_email_token`             ``GET /auth/confirmed_email/{token}``
``RESET_PASSWORD_TOKEN_SCOPE``    :func:`create_password_reset_token`    ``POST /auth/reset-password/confirm``
================================  =====================================  ======================================

Example
-------

.. code-block:: python

    from src.services.auth import create_access_token, decode_token, ACCESS_TOKEN_SCOPE

    token = create_access_token("alice@example.com")
    email = decode_token(token, ACCESS_TOKEN_SCOPE)
    assert email == "alice@example.com"
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

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
"""Passlib context. Bcrypt is the only allowed scheme."""

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
"""FastAPI security dependency that extracts a Bearer token from the request."""

ACCESS_TOKEN_SCOPE = "access_token"
REFRESH_TOKEN_SCOPE = "refresh_token"
EMAIL_TOKEN_SCOPE = "email_token"
RESET_PASSWORD_TOKEN_SCOPE = "reset_password_token"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        plain_password: The password supplied by the user (plain text).
        hashed_password: The bcrypt hash stored on :class:`User.hashed_password`.

    Returns:
        ``True`` when the hashes match, ``False`` otherwise. Returns
        ``False`` (rather than raising) when the stored hash is malformed.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password with bcrypt.

    Args:
        password: Plain-text password (already validated by the schema layer
            for length / complexity rules).

    Returns:
        A bcrypt hash string suitable for storing in the database.
    """
    return pwd_context.hash(password)


def _create_token(
    data: dict,
    expires_delta: timedelta,
    scope: str,
    jti: Optional[str] = None,
) -> str:
    """Build and sign a JWT.

    Internal helper — callers should use :func:`create_access_token`,
    :func:`create_refresh_token`, :func:`create_email_token`, or
    :func:`create_password_reset_token` instead.

    Args:
        data: Custom claims (``sub`` should already be set by the caller).
        expires_delta: Lifetime of the token; ``exp`` is computed from now.
        scope: Required custom claim that :func:`decode_token` will check.
        jti: Optional unique token identifier. When supplied, the JTI is
            embedded so the token can be tracked / single-use enforced.

    Returns:
        Signed JWT string (HS256 by default).
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    to_encode.update({"iat": now, "exp": now + expires_delta, "scope": scope})
    if jti is not None:
        to_encode["jti"] = jti
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    """Issue a short-lived **access** JWT.

    Carries the user's email in the ``sub`` claim and lasts for
    ``settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES`` minutes by default.

    Args:
        subject: User identifier — by convention the user's email.
        expires_minutes: Override TTL (used in tests).

    Returns:
        A JWT scoped ``access_token``.
    """
    minutes = expires_minutes or settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    return _create_token({"sub": subject}, timedelta(minutes=minutes), ACCESS_TOKEN_SCOPE)


def create_refresh_token(subject: str, expires_days: Optional[int] = None) -> str:
    """Issue a long-lived **refresh** JWT.

    Used by ``POST /api/auth/refresh`` to obtain a fresh access token
    without re-prompting the user for credentials.

    Args:
        subject: User identifier — by convention the user's email.
        expires_days: Override TTL in days (default from settings).

    Returns:
        A JWT scoped ``refresh_token``.
    """
    days = expires_days or settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    return _create_token({"sub": subject}, timedelta(days=days), REFRESH_TOKEN_SCOPE)


def create_email_token(subject: str) -> str:
    """Issue an **email-verification** JWT delivered via the verification email.

    Args:
        subject: The recipient's email address — also stored in ``sub`` so
            that the confirmation endpoint can look the user up.

    Returns:
        A JWT scoped ``email_token``.
    """
    return _create_token(
        {"sub": subject},
        timedelta(hours=settings.JWT_EMAIL_TOKEN_EXPIRE_HOURS),
        EMAIL_TOKEN_SCOPE,
    )


def create_password_reset_token(subject: str) -> Tuple[str, str]:
    """Issue a single-use **password-reset** JWT.

    The token carries a randomly generated ``jti`` (JWT ID). After a token
    is consumed once, the JTI is recorded in Redis with TTL equal to the
    token lifetime — a second confirmation attempt with the same token is
    rejected by :func:`mark_password_reset_token_used`.

    Args:
        subject: The user's email address.

    Returns:
        A tuple ``(token, jti)``. Callers persist the JTI server-side so
        they can later prevent reuse.
    """
    jti = uuid.uuid4().hex
    token = _create_token(
        {"sub": subject},
        timedelta(minutes=settings.JWT_RESET_PASSWORD_TOKEN_EXPIRE_MINUTES),
        RESET_PASSWORD_TOKEN_SCOPE,
        jti=jti,
    )
    return token, jti


def decode_token(token: str, expected_scope: str) -> str:
    """Validate a JWT and return its ``sub`` claim.

    The function checks signature, expiration, scope, and the presence of
    a non-empty subject — any failure raises **HTTP 401**.

    Args:
        token: Raw JWT string from the request.
        expected_scope: The scope the token must carry. Mismatched scopes
            (e.g. presenting a refresh token where an access token is
            required) raise 401.

    Returns:
        The ``sub`` claim — by convention the user's email address.

    Raises:
        fastapi.HTTPException: 401 with ``WWW-Authenticate: Bearer`` for
            any decode error, expired token, scope mismatch, or missing
            subject.
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


def decode_token_full(token: str, expected_scope: str) -> dict:
    """Like :func:`decode_token` but returns the full payload (including ``jti``).

    Used by the password-reset flow so the caller can read ``jti`` and
    enforce single-use semantics.

    Args:
        token: Raw JWT string.
        expected_scope: Required scope claim.

    Returns:
        The decoded payload dict.

    Raises:
        fastapi.HTTPException: 401 on any validation failure.
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
    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def _ensure_token_not_revoked(user: User, iat_ts: Optional[int]) -> None:
    """Reject tokens minted before the user's most recent password change.

    When a user changes their password (typically through the reset
    flow), :attr:`User.password_changed_at` is bumped to ``now``. Any
    JWT — access or refresh — whose ``iat`` (issued-at) claim predates
    that timestamp is rejected with 401. This is the
    "session-invalidation-after-reset" property that makes a stolen
    token useless once the legitimate user has rotated their password.

    Args:
        user: The user the token claims to authenticate.
        iat_ts: The token's ``iat`` claim (UNIX seconds). Older tokens
            without an ``iat`` (legacy) are passed through unchanged.

    Raises:
        fastapi.HTTPException: 401 ``"Token has been revoked"`` if the
            token predates the password change.
    """
    if iat_ts is None or user.password_changed_at is None:
        return
    iat = datetime.fromtimestamp(int(iat_ts), tz=timezone.utc)
    # SQLite drops timezone info even on a tz-aware column; assume UTC
    # so the comparison against the always-tz-aware iat works on both
    # SQLite (tests) and Postgres (prod).
    pwd_changed = user.password_changed_at
    if pwd_changed.tzinfo is None:
        pwd_changed = pwd_changed.replace(tzinfo=timezone.utc)
    # Allow a 1-second slack to absorb truncation when iat is whole seconds
    # but password_changed_at has microseconds.
    if iat + timedelta(seconds=1) < pwd_changed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a Bearer access token.

    Two layers of validation run in sequence:

    1. **Token shape** — :func:`decode_token_full` checks signature,
       ``exp``, and that ``scope == "access_token"``.
    2. **Token freshness** — after the user is resolved (cache or DB),
       :func:`_ensure_token_not_revoked` verifies that the token's
       ``iat`` is not older than the user's last password change.

    Lookups go **cache-first**: the user is fetched from Redis (keyed
    by email) and only on a cache miss does the function hit the
    database. On a miss, the freshly-loaded :class:`User` is also
    written back to the cache, so subsequent requests during the TTL
    window are cache-served.

    Args:
        token: Bearer token extracted from the ``Authorization`` header by
            FastAPI's :class:`OAuth2PasswordBearer`.
        db: Database session injected by :func:`get_db`.

    Returns:
        The authenticated :class:`User` instance.

    Raises:
        fastapi.HTTPException: 401 on any auth failure — bad token,
            missing user, or token revoked by a more-recent password
            change.

    Example:
        Use it as a FastAPI dependency::

            from fastapi import Depends
            from src.services.auth import get_current_user

            @router.get("/me")
            def me(current_user = Depends(get_current_user)):
                return current_user
    """
    payload = decode_token_full(token, ACCESS_TOKEN_SCOPE)
    email = payload["sub"]
    iat_ts = payload.get("iat")

    cached = user_cache.get_cached_user(email)
    if cached is not None:
        _ensure_token_not_revoked(cached, iat_ts)
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
    _ensure_token_not_revoked(user, iat_ts)
    user_cache.cache_user(user)
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency that 403s any caller whose role is not :attr:`UserRole.ADMIN`.

    Args:
        current_user: The user resolved by :func:`get_current_user`.

    Returns:
        The same :class:`User`, unchanged, when the role check passes.

    Raises:
        fastapi.HTTPException: 403 ``"Admin privileges required"`` for
            non-admin callers.

    Example:
        Protect an endpoint::

            @router.get("/admin/users", dependencies=[Depends(require_admin)])
            def list_all_users(...):
                ...
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
