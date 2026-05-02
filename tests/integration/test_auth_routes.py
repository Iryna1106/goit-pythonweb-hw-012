"""Integration tests for ``/api/auth`` routes."""
from __future__ import annotations

from src.repository import users as repo_users
from src.services import auth as auth_service


def test_register_creates_user(client, db_session):
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "newbie",
            "email": "newbie@example.com",
            "password": "pwd1234",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "newbie@example.com"
    assert body["confirmed"] is False
    assert body["role"] == "user"

    persisted = repo_users.get_user_by_email(db_session, "newbie@example.com")
    assert persisted is not None


def test_register_conflict_email(client, confirmed_user):
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "new",
            "email": confirmed_user.email,
            "password": "pwd1234",
        },
    )
    assert resp.status_code == 409


def test_register_conflict_username(client, confirmed_user):
    resp = client.post(
        "/api/auth/register",
        json={
            "username": confirmed_user.username,
            "email": "another@example.com",
            "password": "pwd1234",
        },
    )
    assert resp.status_code == 409


def test_login_success_returns_token_pair(client, confirmed_user):
    resp = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "str0ngP@ss"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]


def test_login_login_via_username_works(client, confirmed_user):
    resp = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.username, "password": "str0ngP@ss"},
    )
    assert resp.status_code == 200


def test_login_wrong_password(client, confirmed_user):
    resp = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "WRONG"},
    )
    assert resp.status_code == 401


def test_login_unconfirmed_user_blocked(client, user_factory):
    user_factory(
        username="pending",
        email="pending@example.com",
        confirmed=False,
    )
    resp = client.post(
        "/api/auth/login",
        data={"username": "pending@example.com", "password": "str0ngP@ss"},
    )
    assert resp.status_code == 401


def test_refresh_returns_new_pair(client, confirmed_user):
    login = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "str0ngP@ss"},
    ).json()
    resp = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_refresh_rejects_access_token(client, confirmed_user):
    login = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "str0ngP@ss"},
    ).json()
    resp = client.post("/api/auth/refresh", json={"refresh_token": login["access_token"]})
    assert resp.status_code == 401


def test_confirmed_email_marks_user(client, user_factory):
    user = user_factory(
        username="pending",
        email="pending@example.com",
        confirmed=False,
    )
    token = auth_service.create_email_token(user.email)
    resp = client.get(f"/api/auth/confirmed_email/{token}")
    assert resp.status_code == 200
    # second call returns "already confirmed"
    resp2 = client.get(f"/api/auth/confirmed_email/{token}")
    assert resp2.status_code == 200
    assert "already" in resp2.json()["message"].lower()


def test_confirmed_email_invalid_token(client):
    resp = client.get("/api/auth/confirmed_email/garbage")
    assert resp.status_code == 401


def test_request_email_always_200(client):
    resp = client.post(
        "/api/auth/request_email", json={"email": "anyone@example.com"}
    )
    assert resp.status_code == 200


def test_password_reset_request_always_200(client, confirmed_user):
    resp = client.post(
        "/api/auth/reset-password", json={"email": confirmed_user.email}
    )
    assert resp.status_code == 200
    resp_unknown = client.post(
        "/api/auth/reset-password", json={"email": "noone@example.com"}
    )
    assert resp_unknown.status_code == 200


def test_password_reset_confirm_changes_password(client, confirmed_user, db_session):
    token, _jti = auth_service.create_password_reset_token(confirmed_user.email)
    resp = client.post(
        "/api/auth/reset-password/confirm",
        json={"token": token, "new_password": "newpass12"},
    )
    assert resp.status_code == 200

    # Old password no longer works.
    bad = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "str0ngP@ss"},
    )
    assert bad.status_code == 401

    good = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "newpass12"},
    )
    assert good.status_code == 200


def test_password_reset_confirm_invalid_token(client):
    resp = client.post(
        "/api/auth/reset-password/confirm",
        json={"token": "garbage", "new_password": "newpass12"},
    )
    assert resp.status_code == 401
