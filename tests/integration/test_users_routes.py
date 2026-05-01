"""Integration tests for ``/api/users`` routes."""
from __future__ import annotations

import io


def test_me_requires_auth(client):
    resp = client.get("/api/users/me")
    assert resp.status_code == 401


def test_me_returns_profile(client, confirmed_user, auth_headers):
    resp = client.get("/api/users/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == confirmed_user.email
    assert body["role"] == "user"


def test_avatar_update_blocked_for_regular_user(client, auth_headers):
    fake = io.BytesIO(b"PNGDATA")
    resp = client.patch(
        "/api/users/avatar",
        headers=auth_headers,
        files={"file": ("a.png", fake, "image/png")},
    )
    assert resp.status_code == 403


def test_avatar_update_allowed_for_admin(client, admin_headers, admin_user):
    fake = io.BytesIO(b"PNGDATA")
    resp = client.patch(
        "/api/users/avatar",
        headers=admin_headers,
        files={"file": ("a.png", fake, "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["avatar"].startswith("https://cdn.example/")
