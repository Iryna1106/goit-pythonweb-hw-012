"""Redis-backed cache helpers for the Contacts REST API.

Two responsibilities live here:

1. **Authenticated-user cache.** :func:`get_current_user` calls
   :func:`get_cached_user` before touching the database. After a DB load
   it stores the user via :func:`cache_user`. Any code that mutates
   user state (avatar, password, role, email confirmation) must call
   :func:`invalidate_user` so a stale cached row is not returned to the
   next request.

2. **Single-use password-reset tokens.** :func:`mark_password_reset_token_used`
   atomically claims a token's JTI in Redis. A second confirmation
   attempt with the same token observes the marker and is rejected
   even if the JWT itself has not yet expired.

Failure modes
-------------

The module is **best-effort** — every helper degrades gracefully when
Redis is unavailable. ``get_cached_user`` returns ``None`` (which forces
a database load), ``cache_user`` and ``invalidate_user`` are no-ops, and
``mark_password_reset_token_used`` falls back to a permissive ``True``
so password resets keep working when the cache is offline. The trade-off
is intentional: caching is an optimisation, password reset is correctness.

When Redis *is* available, the JTI-based reuse check is enforced
strictly and a replayed token returns 400.

Keys used
---------

* ``user:<email>`` — JSON-serialised :class:`User` row.
* ``pwreset:used:<jti>`` — sentinel ``"1"`` for consumed reset tokens.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

import redis

from src.conf.config import settings
from src.database.models import User, UserRole

log = logging.getLogger(__name__)

_client: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    """Return the process-wide :class:`redis.Redis` client, or ``None`` if unreachable.

    The client is created on the first call and reused for the lifetime
    of the process. Connectivity is verified with ``PING`` once; if it
    fails, the function caches ``None`` and silently disables every
    cache helper for the rest of the process. This keeps the API alive
    in dev environments where Redis is not running.

    Returns:
        A connected :class:`redis.Redis` instance, or ``None`` when no
        Redis is reachable.
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


def reset_redis_client() -> None:
    """Forget the cached Redis client (used by tests to reconnect to a fake)."""
    global _client
    _client = None


def _user_key(email: str) -> str:
    """Return the Redis key under which the given user is cached."""
    return f"user:{email.lower()}"


def _reset_jti_key(jti: str) -> str:
    """Return the Redis key that marks a consumed password-reset token."""
    return f"pwreset:used:{jti}"


def _serialize_user(user: User) -> str:
    """Encode a :class:`User` ORM instance as a JSON string for Redis storage."""
    return json.dumps(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "hashed_password": user.hashed_password,
            "avatar": user.avatar,
            "confirmed": user.confirmed,
            "role": user.role.value if isinstance(user.role, UserRole) else str(user.role),
            "password_changed_at": (
                user.password_changed_at.isoformat() if user.password_changed_at else None
            ),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
    )


def _deserialize_user(raw: str) -> User:
    """Hydrate a :class:`User` instance from its JSON form (inverse of :func:`_serialize_user`)."""
    data = json.loads(raw)
    user = User()
    user.id = data["id"]
    user.username = data["username"]
    user.email = data["email"]
    user.hashed_password = data["hashed_password"]
    user.avatar = data.get("avatar")
    user.confirmed = data["confirmed"]
    user.role = UserRole(data.get("role", UserRole.USER.value))
    user.password_changed_at = (
        datetime.fromisoformat(data["password_changed_at"])
        if data.get("password_changed_at")
        else None
    )
    user.created_at = (
        datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
    )
    user.updated_at = (
        datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
    )
    return user


def get_cached_user(email: str) -> Optional[User]:
    """Look up a cached user by email.

    Args:
        email: Case-insensitive email address.

    Returns:
        A hydrated :class:`User` instance on cache hit, ``None`` on miss
        (or when Redis is unavailable).
    """
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
    """Store a user in Redis under their email, with TTL.

    Args:
        user: The ORM row to cache.
        ttl_seconds: Override TTL; defaults to
            :attr:`settings.REDIS_USER_CACHE_TTL_SECONDS`.
    """
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
    """Drop the cached user keyed by ``email`` (no-op when Redis is offline)."""
    client = get_redis()
    if client is None:
        return
    try:
        client.delete(_user_key(email))
    except Exception as exc:  # pragma: no cover
        log.warning("Redis DEL failed: %s", exc)


def mark_password_reset_token_used(jti: str, ttl_seconds: int) -> bool:
    """Atomically claim a reset-token JTI as consumed.

    Implemented with ``SET NX EX`` so the first caller wins and any later
    confirmation attempt observes the existing key. The TTL matches the
    token's remaining life so we don't leak keys forever.

    Args:
        jti: The token's unique identifier (``jti`` claim).
        ttl_seconds: How long to remember the JTI — should be at least
            the token's remaining lifetime.

    Returns:
        ``True`` if this call successfully claimed the JTI (i.e. token
        was unused) — caller may proceed. ``False`` if the JTI was
        already claimed earlier (replay attempt). When Redis is offline
        the function returns ``True`` so resets keep working without a
        cache; in production both should be available.
    """
    client = get_redis()
    if client is None:
        # Best-effort: no cache → no replay protection, but still allow
        # the reset rather than locking users out when Redis is down.
        return True
    try:
        # set(... nx=True) returns truthy only when the key didn't exist.
        ok = client.set(_reset_jti_key(jti), "1", nx=True, ex=max(ttl_seconds, 1))
    except Exception as exc:  # pragma: no cover
        log.warning("Redis NX SET failed: %s", exc)
        return True
    return bool(ok)
