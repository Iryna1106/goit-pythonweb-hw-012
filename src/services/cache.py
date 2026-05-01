"""Tiny Redis wrapper used to cache the current user.

The module exposes a single lazily-constructed :class:`redis.Redis` client and
helpers for serialising / fetching / invalidating cached :class:`User` rows.
Failures (e.g. Redis is down) never propagate — the app falls back to the
database transparently.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import redis

from src.conf.config import settings
from src.database.models import User, UserRole

log = logging.getLogger(__name__)

_client: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    """Return a process-wide :class:`redis.Redis` client.

    Returns ``None`` if a connection cannot be established. Callers must
    treat the cache as best-effort — every helper degrades gracefully when
    Redis is unavailable.
    """
    global _client
    if _client is not None:
        return _client
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.ping()
        _client = client
    except Exception as exc:  # pragma: no cover - depends on environment
        log.warning("Redis unavailable, caching disabled: %s", exc)
        _client = None
    return _client


def _user_key(email: str) -> str:
    return f"user:{email.lower()}"


def _serialize_user(user: User) -> str:
    return json.dumps(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "hashed_password": user.hashed_password,
            "avatar": user.avatar,
            "confirmed": user.confirmed,
            "role": user.role.value if isinstance(user.role, UserRole) else str(user.role),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
    )


def _deserialize_user(raw: str) -> User:
    from datetime import datetime

    data = json.loads(raw)
    user = User()
    user.id = data["id"]
    user.username = data["username"]
    user.email = data["email"]
    user.hashed_password = data["hashed_password"]
    user.avatar = data.get("avatar")
    user.confirmed = data["confirmed"]
    user.role = UserRole(data.get("role", UserRole.USER.value))
    user.created_at = (
        datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
    )
    user.updated_at = (
        datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
    )
    return user


def get_cached_user(email: str) -> Optional[User]:
    """Return a hydrated :class:`User` from the cache, or ``None`` if missing."""
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(_user_key(email))
    except Exception as exc:  # pragma: no cover
        log.warning("Redis GET failed: %s", exc)
        return None
    if raw is None:
        return None
    try:
        return _deserialize_user(raw)
    except Exception as exc:  # pragma: no cover
        log.warning("Failed to deserialize cached user: %s", exc)
        return None


def cache_user(user: User, ttl_seconds: Optional[int] = None) -> None:
    """Store ``user`` under its email key for ``ttl_seconds`` (default from settings)."""
    client = get_redis()
    if client is None:
        return
    try:
        client.set(
            _user_key(user.email),
            _serialize_user(user),
            ex=ttl_seconds or settings.REDIS_USER_CACHE_TTL_SECONDS,
        )
    except Exception as exc:  # pragma: no cover
        log.warning("Redis SET failed: %s", exc)


def invalidate_user(email: str) -> None:
    """Drop the cached user keyed by ``email`` (no-op if not cached)."""
    client = get_redis()
    if client is None:
        return
    try:
        client.delete(_user_key(email))
    except Exception as exc:  # pragma: no cover
        log.warning("Redis DEL failed: %s", exc)
