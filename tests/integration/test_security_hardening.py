"""Security-hardening tests for the password-reset flow.

Verifies the four properties added in revision 2:

1. Access tokens issued *before* a successful password reset are
   rejected as revoked (``Token has been revoked``).
2. Refresh tokens behave the same way.
3. The post-reset notification email is dispatched.
4. The ``/reset-password`` endpoint is rate-limited.
"""
from __future__ import annotations

import time

import pytest

from src.services import auth as auth_service


# ---------------------------------------------------------------------------
# Token invalidation after password change
# ---------------------------------------------------------------------------

def test_access_token_revoked_after_password_reset(client, confirmed_user):
    """A token issued before reset must NOT work after the reset completes."""
    # Login → get access + refresh.
    login = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "str0ngP@ss"},
    ).json()
    old_access = login["access_token"]
    auth = {"Authorization": f"Bearer {old_access}"}

    # Token works right now.
    assert client.get("/api/users/me", headers=auth).status_code == 200

    # Sleep a tick so password_changed_at > token's iat (iat is whole seconds).
    time.sleep(1.1)

    # Reset the password.
    token, _jti = auth_service.create_password_reset_token(confirmed_user.email)
    r = client.post(
        "/api/auth/reset-password/confirm",
        json={"token": token, "new_password": "rotated-pw"},
    )
    assert r.status_code == 200

    # Old token is now revoked.
    r = client.get("/api/users/me", headers=auth)
    assert r.status_code == 401
    assert "revoked" in r.json()["detail"].lower()


def test_refresh_token_revoked_after_password_reset(client, confirmed_user):
    """A refresh token issued before reset cannot mint a new access token."""
    login = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "str0ngP@ss"},
    ).json()
    old_refresh = login["refresh_token"]

    time.sleep(1.1)

    # Reset.
    token, _jti = auth_service.create_password_reset_token(confirmed_user.email)
    client.post(
        "/api/auth/reset-password/confirm",
        json={"token": token, "new_password": "rotated-pw"},
    )

    # Old refresh is dead.
    r = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 401


def test_new_token_after_reset_works(client, confirmed_user):
    """After resetting, logging in with the new password issues a working token."""
    time.sleep(1.1)
    token, _jti = auth_service.create_password_reset_token(confirmed_user.email)
    client.post(
        "/api/auth/reset-password/confirm",
        json={"token": token, "new_password": "rotated-pw"},
    )

    new_login = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "rotated-pw"},
    ).json()
    auth = {"Authorization": f"Bearer {new_login['access_token']}"}
    assert client.get("/api/users/me", headers=auth).status_code == 200


# ---------------------------------------------------------------------------
# Post-reset notification email
# ---------------------------------------------------------------------------

def test_password_changed_notice_dispatched(client, confirmed_user, monkeypatch):
    """The notification email helper is invoked exactly once on success."""
    calls: list[tuple] = []

    async def _record(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("src.api.auth.send_password_changed_notice", _record)

    token, _jti = auth_service.create_password_reset_token(confirmed_user.email)
    r = client.post(
        "/api/auth/reset-password/confirm",
        json={"token": token, "new_password": "another-pw1"},
    )
    assert r.status_code == 200
    assert len(calls) == 1
    args, _kwargs = calls[0]
    # send_password_changed_notice(email, username, base_url)
    assert args[0] == confirmed_user.email
    assert args[1] == confirmed_user.username


# ---------------------------------------------------------------------------
# Rate limit on /reset-password
# ---------------------------------------------------------------------------

def test_reset_password_request_rate_limit(client, confirmed_user):
    """Burst beyond 3/hour returns 429 — relies on re-enabling the limiter."""
    from src.services.rate_limit import limiter

    # Re-enable for this test only.
    previous = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    try:
        # 3 allowed.
        for _ in range(3):
            r = client.post(
                "/api/auth/reset-password",
                json={"email": confirmed_user.email},
            )
            assert r.status_code == 200, r.text

        # 4th is throttled.
        r = client.post(
            "/api/auth/reset-password", json={"email": confirmed_user.email}
        )
        assert r.status_code == 429
    finally:
        limiter.enabled = previous
        limiter.reset()
