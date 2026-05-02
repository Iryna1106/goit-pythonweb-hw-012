"""End-to-end user scenarios.

These tests stitch together multiple endpoints into realistic flows so
the regression net catches breakage in the *interactions* between the
auth, users, and contacts subsystems — not just the individual handlers.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.services import auth as auth_service
from src.services import cache as cache_service


# ---------------------------------------------------------------------------
# Full happy-path user journey
# ---------------------------------------------------------------------------

def test_full_user_journey(client, db_session):
    """Register → confirm email → login → refresh → CRUD contact → delete."""
    # 1) Register.
    r = client.post(
        "/api/auth/register",
        json={
            "username": "journey",
            "email": "journey@example.com",
            "password": "journeypw1",
        },
    )
    assert r.status_code == 201

    # 2) Confirm email by feeding back the same token the email would carry.
    token = auth_service.create_email_token("journey@example.com")
    r = client.get(f"/api/auth/confirmed_email/{token}")
    assert r.status_code == 200
    assert "successfully confirmed" in r.json()["message"]

    # 3) Login.
    r = client.post(
        "/api/auth/login",
        data={"username": "journey@example.com", "password": "journeypw1"},
    )
    assert r.status_code == 200
    tokens = r.json()
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]
    assert access and refresh

    auth = {"Authorization": f"Bearer {access}"}

    # 4) Profile.
    r = client.get("/api/users/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["email"] == "journey@example.com"
    assert r.json()["role"] == "user"

    # 5) Create a contact.
    r = client.post(
        "/api/contacts/",
        headers=auth,
        json={
            "first_name": "Lina",
            "last_name": "Kostenko",
            "email": "lina@example.com",
            "phone": "+380501230000",
            "birthday": "1930-03-19",
        },
    )
    assert r.status_code == 201
    contact_id = r.json()["id"]

    # 6) Update.
    r = client.put(
        f"/api/contacts/{contact_id}",
        headers=auth,
        json={"phone": "+380509999999"},
    )
    assert r.status_code == 200
    assert r.json()["phone"] == "+380509999999"

    # 7) Refresh — get a brand-new pair, swap in the new access token.
    r = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    new_access = r.json()["access_token"]
    auth_new = {"Authorization": f"Bearer {new_access}"}

    # 8) New token continues to work.
    r = client.get(f"/api/contacts/{contact_id}", headers=auth_new)
    assert r.status_code == 200

    # 9) Delete.
    r = client.delete(f"/api/contacts/{contact_id}", headers=auth_new)
    assert r.status_code == 200
    r = client.get(f"/api/contacts/{contact_id}", headers=auth_new)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Password reset full flow
# ---------------------------------------------------------------------------

def test_password_reset_full_flow(client, confirmed_user):
    """Request reset → confirm with token → log in with new password.

    Old password no longer works after a successful reset.
    """
    # Old password works.
    r = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "str0ngP@ss"},
    )
    assert r.status_code == 200

    # Request reset (emits email — patched out by the integration conftest).
    r = client.post(
        "/api/auth/reset-password", json={"email": confirmed_user.email}
    )
    assert r.status_code == 200

    # Server-side: simulate the token the email would have contained.
    token, _jti = auth_service.create_password_reset_token(confirmed_user.email)

    # Confirm reset.
    r = client.post(
        "/api/auth/reset-password/confirm",
        json={"token": token, "new_password": "fresh-pass-9"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == confirmed_user.email

    # Old password rejected.
    r = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "str0ngP@ss"},
    )
    assert r.status_code == 401

    # New password works.
    r = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "fresh-pass-9"},
    )
    assert r.status_code == 200


def test_reset_token_is_single_use(client, confirmed_user, monkeypatch):
    """A reset token cannot be replayed — second confirm with the same token returns 400.

    Single-use is enforced via the JTI marker in Redis. We use a tiny
    in-memory dict to stand in for Redis here (no external dependency).
    """
    used: set[str] = set()

    def _mark(jti: str, ttl: int) -> bool:
        if jti in used:
            return False
        used.add(jti)
        return True

    monkeypatch.setattr(cache_service, "mark_password_reset_token_used", _mark)

    token, _jti = auth_service.create_password_reset_token(confirmed_user.email)

    r1 = client.post(
        "/api/auth/reset-password/confirm",
        json={"token": token, "new_password": "first-new-1"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/auth/reset-password/confirm",
        json={"token": token, "new_password": "second-try-2"},
    )
    assert r2.status_code == 400
    assert "already been used" in r2.json()["detail"]


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------

def test_users_cannot_see_each_others_contacts(client, user_factory):
    """A contact owned by user A is invisible to user B."""
    a = user_factory(username="alice", email="alice@example.com")
    b = user_factory(username="bob", email="bob@example.com")

    # Login both.
    a_token = client.post(
        "/api/auth/login",
        data={"username": a.email, "password": "str0ngP@ss"},
    ).json()["access_token"]
    b_token = client.post(
        "/api/auth/login",
        data={"username": b.email, "password": "str0ngP@ss"},
    ).json()["access_token"]
    a_auth = {"Authorization": f"Bearer {a_token}"}
    b_auth = {"Authorization": f"Bearer {b_token}"}

    # Alice creates a contact.
    r = client.post(
        "/api/contacts/",
        headers=a_auth,
        json={
            "first_name": "Secret",
            "last_name": "Contact",
            "email": "secret@example.com",
            "phone": "+380501110001",
            "birthday": "1990-01-01",
        },
    )
    assert r.status_code == 201
    cid = r.json()["id"]

    # Alice sees it.
    assert client.get(f"/api/contacts/{cid}", headers=a_auth).status_code == 200

    # Bob does not.
    assert client.get(f"/api/contacts/{cid}", headers=b_auth).status_code == 404

    # Bob's list is empty; Alice's has one.
    assert client.get("/api/contacts/", headers=a_auth).json() != []
    assert client.get("/api/contacts/", headers=b_auth).json() == []


# ---------------------------------------------------------------------------
# Admin user-management routes
# ---------------------------------------------------------------------------

def test_admin_can_list_users_regular_user_cannot(
    client, admin_headers, auth_headers, confirmed_user, admin_user
):
    """``GET /api/users/`` is admin-only."""
    # Regular user → 403.
    r = client.get("/api/users/", headers=auth_headers)
    assert r.status_code == 403

    # Admin → 200, includes both users.
    r = client.get("/api/users/", headers=admin_headers)
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert confirmed_user.email in emails
    assert admin_user.email in emails


def test_admin_can_promote_user(client, admin_headers, confirmed_user):
    """An admin can promote a regular user to admin via PATCH /{id}/role."""
    r = client.patch(
        f"/api/users/{confirmed_user.id}/role",
        headers=admin_headers,
        json={"role": "admin"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_admin_cannot_self_demote(client, admin_headers, admin_user):
    """An admin demoting themselves is blocked to avoid lockouts."""
    r = client.patch(
        f"/api/users/{admin_user.id}/role",
        headers=admin_headers,
        json={"role": "user"},
    )
    assert r.status_code == 400
    assert "own role" in r.json()["detail"]


def test_role_update_unknown_user_404(client, admin_headers):
    r = client.patch(
        "/api/users/9999/role",
        headers=admin_headers,
        json={"role": "admin"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Refresh token edge cases
# ---------------------------------------------------------------------------

def test_refresh_for_deleted_user_returns_401(client, db_session, confirmed_user):
    """A refresh issued for a user that has since been deleted is rejected."""
    refresh = client.post(
        "/api/auth/login",
        data={"username": confirmed_user.email, "password": "str0ngP@ss"},
    ).json()["refresh_token"]

    db_session.delete(confirmed_user)
    db_session.commit()

    r = client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Upcoming birthdays — sanity check the date math through the API
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("offset_days", [1, 5, 7])
def test_upcoming_birthdays_includes_contacts_within_window(
    client, auth_headers, offset_days
):
    bday = date.today() + timedelta(days=offset_days)
    r = client.post(
        "/api/contacts/",
        headers=auth_headers,
        json={
            "first_name": f"Soon{offset_days}",
            "last_name": "Bday",
            "email": f"soon{offset_days}@example.com",
            "phone": "+380501230000",
            "birthday": f"1990-{bday.month:02d}-{bday.day:02d}",
        },
    )
    assert r.status_code == 201

    r = client.get("/api/contacts/upcoming-birthdays?days=7", headers=auth_headers)
    assert r.status_code == 200
    assert any(c["email"] == f"soon{offset_days}@example.com" for c in r.json())
