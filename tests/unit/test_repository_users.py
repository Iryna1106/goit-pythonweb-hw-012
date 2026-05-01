"""Unit tests for :mod:`src.repository.users`."""
from __future__ import annotations

from src.database.models import User, UserRole
from src.repository import users as repo_users
from src.schemas.users import UserCreate


def test_get_user_by_email_returns_persisted_user(db_session, confirmed_user):
    user = repo_users.get_user_by_email(db_session, confirmed_user.email)
    assert user is not None
    assert user.id == confirmed_user.id


def test_get_user_by_email_returns_none_when_missing(db_session):
    assert repo_users.get_user_by_email(db_session, "nope@example.com") is None


def test_get_user_by_username_returns_persisted_user(db_session, confirmed_user):
    user = repo_users.get_user_by_username(db_session, confirmed_user.username)
    assert user is not None
    assert user.email == confirmed_user.email


def test_create_user_persists_and_hashes_password(db_session):
    body = UserCreate(username="new_user", email="new@example.com", password="pwd1234")
    user = repo_users.create_user(db_session, body)

    assert user.id is not None
    assert user.username == "new_user"
    assert user.email == "new@example.com"
    assert user.confirmed is False
    assert user.role == UserRole.USER
    assert user.hashed_password != "pwd1234"


def test_create_user_with_admin_role(db_session):
    body = UserCreate(username="root", email="root@example.com", password="pwd1234")
    user = repo_users.create_user(db_session, body, role=UserRole.ADMIN)
    assert user.role == UserRole.ADMIN


def test_confirm_email_marks_user_confirmed(db_session, user_factory):
    user = user_factory(confirmed=False, email="x@example.com", username="x")
    out = repo_users.confirm_email(db_session, user.email)
    assert out is not None
    assert out.confirmed is True


def test_confirm_email_returns_none_when_unknown(db_session):
    assert repo_users.confirm_email(db_session, "unknown@example.com") is None


def test_update_avatar_writes_url(db_session, confirmed_user):
    out = repo_users.update_avatar(db_session, confirmed_user.email, "https://cdn/x")
    assert out is not None
    assert out.avatar == "https://cdn/x"


def test_update_avatar_returns_none_when_unknown(db_session):
    assert repo_users.update_avatar(db_session, "nope@example.com", "u") is None


def test_update_password_changes_hash(db_session, confirmed_user):
    old_hash = confirmed_user.hashed_password
    out = repo_users.update_password(db_session, confirmed_user.email, "brand-new-pass")
    assert out is not None
    assert out.hashed_password != old_hash


def test_update_password_returns_none_when_unknown(db_session):
    assert repo_users.update_password(db_session, "ghost@example.com", "x") is None


def test_set_role_promotes_user(db_session, confirmed_user):
    out = repo_users.set_role(db_session, confirmed_user.email, UserRole.ADMIN)
    assert out is not None
    assert out.role == UserRole.ADMIN


def test_set_role_returns_none_when_unknown(db_session):
    assert repo_users.set_role(db_session, "no@example.com", UserRole.ADMIN) is None
