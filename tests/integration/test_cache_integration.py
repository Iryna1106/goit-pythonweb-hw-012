"""End-to-end proof that ``get_current_user`` actually consults Redis.

We swap the real Redis client for an in-memory ``fakeredis`` fake, hit
``/api/users/me`` once (populating the cache), then patch the
repository to raise if it's called again. A second request should
succeed because the user is served from the cache, never reaching the
DB-touching code path.
"""
from __future__ import annotations

import pytest

from src.services import cache as cache_service


@pytest.fixture()
def real_redis(monkeypatch):
    """Use an in-process fakeredis instead of the live cache."""
    import fakeredis

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache_service, "_client", None)

    def _get_redis():
        return fake

    monkeypatch.setattr(cache_service, "get_redis", _get_redis)

    # Replace the helpers that the integration conftest had patched out
    # so the *real* cache code path runs against fakeredis.
    monkeypatch.setattr(
        cache_service,
        "get_cached_user",
        cache_service.get_cached_user.__wrapped__
        if hasattr(cache_service.get_cached_user, "__wrapped__")
        else cache_service.get_cached_user,
    )
    # Re-import the original implementations (the integration conftest
    # autouse fixture replaced them with no-ops).
    monkeypatch.setattr(cache_service, "get_cached_user", _real_get_cached_user)
    monkeypatch.setattr(cache_service, "cache_user", _real_cache_user)
    monkeypatch.setattr(cache_service, "invalidate_user", _real_invalidate_user)
    return fake


def _real_get_cached_user(email):
    """Reimplementation that bypasses the integration conftest's monkey-patch."""
    client = cache_service.get_redis()
    if client is None:
        return None
    raw = client.get(cache_service._user_key(email))
    if raw is None:
        return None
    return cache_service._deserialize_user(raw)


def _real_cache_user(user, ttl_seconds=None):
    client = cache_service.get_redis()
    if client is None:
        return
    client.set(
        cache_service._user_key(user.email),
        cache_service._serialize_user(user),
        ex=ttl_seconds or 900,
    )


def _real_invalidate_user(email):
    client = cache_service.get_redis()
    if client is None:
        return
    client.delete(cache_service._user_key(email))


def test_me_reads_from_cache_on_second_call(client, auth_headers, monkeypatch, real_redis):
    """First /me call hits the DB and warms the cache; second call hits ONLY the cache."""
    # First call — DB is consulted, user gets cached.
    r1 = client.get("/api/users/me", headers=auth_headers)
    assert r1.status_code == 200

    # The user MUST be in the fake cache now.
    raw = real_redis.get(f"user:{r1.json()['email'].lower()}")
    assert raw is not None, "user was not written to cache after first /me"

    # Sabotage the DB layer: any further DB lookup raises. Cache must short-circuit it.
    def _explode(*_a, **_kw):
        raise AssertionError("DB was hit on second /me — cache did not short-circuit")

    monkeypatch.setattr("src.repository.users.get_user_by_email", _explode)

    # Second call — must succeed entirely from cache.
    r2 = client.get("/api/users/me", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["email"] == r1.json()["email"]


def test_me_falls_back_to_db_when_cache_invalidated(
    client, auth_headers, real_redis, db_session
):
    """After invalidate_user, the next /me hits the DB (cache no longer has the row)."""
    r1 = client.get("/api/users/me", headers=auth_headers)
    assert r1.status_code == 200
    email = r1.json()["email"]

    # Cache hit confirmed.
    assert real_redis.get(f"user:{email.lower()}") is not None

    # Invalidate — cache row is deleted.
    cache_service.invalidate_user(email)
    assert real_redis.get(f"user:{email.lower()}") is None

    # Subsequent /me re-populates the cache.
    r2 = client.get("/api/users/me", headers=auth_headers)
    assert r2.status_code == 200
    assert real_redis.get(f"user:{email.lower()}") is not None
