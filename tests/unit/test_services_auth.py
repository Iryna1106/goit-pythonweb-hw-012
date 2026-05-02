"""Unit tests for :mod:`src.services.auth`."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.services import auth as auth_service


def test_password_hash_roundtrip():
    h = auth_service.get_password_hash("secret-pw")
    assert h != "secret-pw"
    assert auth_service.verify_password("secret-pw", h) is True
    assert auth_service.verify_password("WRONG", h) is False


def test_create_and_decode_access_token():
    token = auth_service.create_access_token("alice@example.com")
    sub = auth_service.decode_token(token, auth_service.ACCESS_TOKEN_SCOPE)
    assert sub == "alice@example.com"


def test_create_and_decode_refresh_token():
    token = auth_service.create_refresh_token("alice@example.com")
    sub = auth_service.decode_token(token, auth_service.REFRESH_TOKEN_SCOPE)
    assert sub == "alice@example.com"


def test_create_and_decode_email_token():
    token = auth_service.create_email_token("alice@example.com")
    sub = auth_service.decode_token(token, auth_service.EMAIL_TOKEN_SCOPE)
    assert sub == "alice@example.com"


def test_create_and_decode_password_reset_token():
    token, jti = auth_service.create_password_reset_token("alice@example.com")
    sub = auth_service.decode_token(token, auth_service.RESET_PASSWORD_TOKEN_SCOPE)
    assert sub == "alice@example.com"
    assert jti and len(jti) >= 16

    # decode_token_full also works and exposes jti.
    payload = auth_service.decode_token_full(token, auth_service.RESET_PASSWORD_TOKEN_SCOPE)
    assert payload["sub"] == "alice@example.com"
    assert payload["jti"] == jti


def test_decode_token_rejects_wrong_scope():
    token = auth_service.create_access_token("alice@example.com")
    with pytest.raises(HTTPException) as exc:
        auth_service.decode_token(token, auth_service.REFRESH_TOKEN_SCOPE)
    assert exc.value.status_code == 401


def test_decode_token_rejects_garbage():
    with pytest.raises(HTTPException) as exc:
        auth_service.decode_token("not-a-token", auth_service.ACCESS_TOKEN_SCOPE)
    assert exc.value.status_code == 401


def test_require_admin_blocks_user(confirmed_user):
    with pytest.raises(HTTPException) as exc:
        auth_service.require_admin(current_user=confirmed_user)
    assert exc.value.status_code == 403


def test_require_admin_allows_admin(admin_user):
    assert auth_service.require_admin(current_user=admin_user) is admin_user


def test_get_current_user_uses_cache(monkeypatch, confirmed_user, db_session):
    """When the cache returns a user, the DB is never touched."""
    monkeypatch.setattr(
        "src.services.cache.get_cached_user", lambda email: confirmed_user
    )
    token = auth_service.create_access_token(confirmed_user.email)

    sentinel = object()
    monkeypatch.setattr(
        "src.repository.users.get_user_by_email", lambda *_a, **_kw: sentinel
    )

    out = auth_service.get_current_user(token=token, db=db_session)
    assert out is confirmed_user  # came from cache, not the DB sentinel


def test_get_current_user_caches_on_miss(monkeypatch, confirmed_user, db_session):
    cached = {}

    def _set_cache(user, ttl_seconds=None):
        cached["user"] = user

    monkeypatch.setattr("src.services.cache.get_cached_user", lambda email: None)
    monkeypatch.setattr("src.services.cache.cache_user", _set_cache)

    token = auth_service.create_access_token(confirmed_user.email)
    out = auth_service.get_current_user(token=token, db=db_session)
    assert out.email == confirmed_user.email
    assert cached["user"].email == confirmed_user.email


def test_get_current_user_404_user_missing(monkeypatch, db_session):
    monkeypatch.setattr("src.services.cache.get_cached_user", lambda email: None)
    token = auth_service.create_access_token("ghost@example.com")
    with pytest.raises(HTTPException) as exc:
        auth_service.get_current_user(token=token, db=db_session)
    assert exc.value.status_code == 401
