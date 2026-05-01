"""Unit tests for :mod:`src.services.cache`."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.database.models import User, UserRole
from src.services import cache as cache_service


@pytest.fixture()
def fake_user() -> User:
    user = User()
    user.id = 1
    user.username = "ivan"
    user.email = "ivan@example.com"
    user.hashed_password = "$2b$dummy"
    user.avatar = None
    user.confirmed = True
    user.role = UserRole.USER
    now = datetime.now(timezone.utc)
    user.created_at = now
    user.updated_at = now
    return user


def test_serialize_then_deserialize_user(fake_user):
    raw = cache_service._serialize_user(fake_user)
    out = cache_service._deserialize_user(raw)
    assert out.id == fake_user.id
    assert out.email == fake_user.email
    assert out.role == UserRole.USER
    assert out.confirmed is True


def test_get_cached_user_returns_none_when_no_client(monkeypatch):
    monkeypatch.setattr(cache_service, "get_redis", lambda: None)
    assert cache_service.get_cached_user("x@example.com") is None


def test_get_cached_user_returns_none_when_missing(monkeypatch):
    client = MagicMock()
    client.get.return_value = None
    monkeypatch.setattr(cache_service, "get_redis", lambda: client)
    assert cache_service.get_cached_user("x@example.com") is None
    client.get.assert_called_once()


def test_get_cached_user_hydrates(monkeypatch, fake_user):
    client = MagicMock()
    client.get.return_value = cache_service._serialize_user(fake_user)
    monkeypatch.setattr(cache_service, "get_redis", lambda: client)
    out = cache_service.get_cached_user(fake_user.email)
    assert out is not None
    assert out.email == fake_user.email


def test_cache_user_calls_set_with_ttl(monkeypatch, fake_user):
    client = MagicMock()
    monkeypatch.setattr(cache_service, "get_redis", lambda: client)
    cache_service.cache_user(fake_user, ttl_seconds=42)
    args, kwargs = client.set.call_args
    assert args[0] == f"user:{fake_user.email.lower()}"
    assert kwargs["ex"] == 42


def test_cache_user_noop_without_redis(monkeypatch, fake_user):
    monkeypatch.setattr(cache_service, "get_redis", lambda: None)
    cache_service.cache_user(fake_user)  # must not raise


def test_invalidate_user_calls_delete(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(cache_service, "get_redis", lambda: client)
    cache_service.invalidate_user("x@example.com")
    client.delete.assert_called_once_with("user:x@example.com")


def test_invalidate_user_noop_without_redis(monkeypatch):
    monkeypatch.setattr(cache_service, "get_redis", lambda: None)
    cache_service.invalidate_user("x@example.com")  # must not raise
