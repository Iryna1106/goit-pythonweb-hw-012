"""Shared pytest fixtures.

* In-memory SQLite engine + session for integration tests.
* Override of ``get_db`` so the FastAPI app uses the test session.
"""
from __future__ import annotations

import os

# Make settings deterministic before any application import reads them.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("APP_BASE_URL", "http://testserver")

from typing import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.db import Base, get_db
from src.database.models import User, UserRole
from src.services import auth as auth_service


@pytest.fixture()
def db_engine():
    """Create a fresh in-memory SQLite engine with all tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Iterator:
    """Yield a transactional session bound to the in-memory engine."""
    SessionLocal = sessionmaker(
        bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session) -> Iterator[TestClient]:
    """FastAPI ``TestClient`` wired up to the in-memory DB session."""
    from main import app

    def _override_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def _make_user(
    db_session,
    *,
    username: str = "ivan",
    email: str = "ivan@example.com",
    password: str = "str0ngP@ss",
    confirmed: bool = True,
    role: UserRole = UserRole.USER,
) -> User:
    user = User(
        username=username,
        email=email,
        hashed_password=auth_service.get_password_hash(password),
        confirmed=confirmed,
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def user_factory(db_session):
    """Factory fixture that creates and persists a :class:`User`."""
    def _factory(**kwargs) -> User:
        return _make_user(db_session, **kwargs)
    return _factory


@pytest.fixture()
def confirmed_user(user_factory) -> User:
    return user_factory()


@pytest.fixture()
def admin_user(user_factory) -> User:
    return user_factory(
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN,
    )


@pytest.fixture()
def auth_headers(client, confirmed_user):
    """Login the default user and return Authorization headers."""
    resp = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "str0ngP@ss"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client, admin_user):
    resp = client.post(
        "/api/auth/login",
        data={"username": admin_user.email, "password": "str0ngP@ss"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def mock_session() -> MagicMock:
    """A ``MagicMock`` standing in for a SQLAlchemy ``Session`` (unit tests)."""
    return MagicMock()
