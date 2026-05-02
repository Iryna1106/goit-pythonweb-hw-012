"""Integration-only fixtures (autouse stubs for cache + outbound calls)."""
from __future__ import annotations

import pytest

from src.services import cache as cache_service


@pytest.fixture(autouse=True)
def disable_cache(monkeypatch):
    """Force the Redis client off so route tests rely on the DB for user lookups."""
    monkeypatch.setattr(cache_service, "get_redis", lambda: None)
    monkeypatch.setattr(cache_service, "get_cached_user", lambda email: None)
    monkeypatch.setattr(cache_service, "cache_user", lambda user, ttl_seconds=None: None)
    monkeypatch.setattr(cache_service, "invalidate_user", lambda email: None)
    monkeypatch.setattr(
        cache_service, "mark_password_reset_token_used", lambda jti, ttl: True
    )


@pytest.fixture(autouse=True)
def disable_rate_limit():
    """Turn off SlowAPI for the test session — tests intentionally burst /me."""
    from src.api.users import limiter

    previous = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = previous


@pytest.fixture(autouse=True)
def stub_outbound(monkeypatch):
    """Patch outbound email + Cloudinary calls so tests don't hit the network."""
    async def _noop_email(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "src.services.email.send_verification_email", _noop_email, raising=False
    )
    monkeypatch.setattr(
        "src.services.email.send_password_reset_email", _noop_email, raising=False
    )
    monkeypatch.setattr(
        "src.api.auth.send_verification_email", _noop_email, raising=False
    )
    monkeypatch.setattr(
        "src.api.auth.send_password_reset_email", _noop_email, raising=False
    )

    def _fake_upload(self, file, username):
        return f"https://cdn.example/{username}.png"

    monkeypatch.setattr(
        "src.services.upload_file.UploadFileService.upload_avatar", _fake_upload
    )
