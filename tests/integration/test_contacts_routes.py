"""Integration tests for ``/api/contacts`` routes."""
from __future__ import annotations

from datetime import date, timedelta


CONTACT_PAYLOAD = {
    "first_name": "Ivan",
    "last_name": "Franko",
    "email": "ivan.franko@example.com",
    "phone": "+380501234567",
    "birthday": "1990-05-17",
}


def test_contacts_require_auth(client):
    assert client.get("/api/contacts/").status_code == 401


def test_create_then_read_contact(client, auth_headers):
    create = client.post("/api/contacts/", json=CONTACT_PAYLOAD, headers=auth_headers)
    assert create.status_code == 201
    cid = create.json()["id"]

    got = client.get(f"/api/contacts/{cid}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["email"] == CONTACT_PAYLOAD["email"]


def test_create_duplicate_email_409(client, auth_headers):
    client.post("/api/contacts/", json=CONTACT_PAYLOAD, headers=auth_headers)
    dup = client.post("/api/contacts/", json=CONTACT_PAYLOAD, headers=auth_headers)
    assert dup.status_code == 409


def test_read_contacts_filters(client, auth_headers):
    # Two contacts, filter by first_name.
    c1 = {**CONTACT_PAYLOAD, "email": "a@e.com", "first_name": "Alice"}
    c2 = {**CONTACT_PAYLOAD, "email": "b@e.com", "first_name": "Bob"}
    client.post("/api/contacts/", json=c1, headers=auth_headers)
    client.post("/api/contacts/", json=c2, headers=auth_headers)

    resp = client.get("/api/contacts/?first_name=Ali", headers=auth_headers)
    assert resp.status_code == 200
    bodies = resp.json()
    assert len(bodies) == 1 and bodies[0]["first_name"] == "Alice"


def test_get_missing_contact_404(client, auth_headers):
    assert client.get("/api/contacts/9999", headers=auth_headers).status_code == 404


def test_update_contact(client, auth_headers):
    created = client.post(
        "/api/contacts/", json=CONTACT_PAYLOAD, headers=auth_headers
    ).json()
    resp = client.put(
        f"/api/contacts/{created['id']}",
        json={"phone": "+380501112233"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["phone"] == "+380501112233"


def test_update_email_conflict(client, auth_headers):
    a = client.post(
        "/api/contacts/",
        json={**CONTACT_PAYLOAD, "email": "a@e.com"},
        headers=auth_headers,
    ).json()
    client.post(
        "/api/contacts/",
        json={**CONTACT_PAYLOAD, "email": "b@e.com"},
        headers=auth_headers,
    )
    resp = client.put(
        f"/api/contacts/{a['id']}",
        json={"email": "b@e.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_update_missing_404(client, auth_headers):
    resp = client.put(
        "/api/contacts/9999", json={"phone": "+380501234567"}, headers=auth_headers
    )
    assert resp.status_code == 404


def test_delete_contact(client, auth_headers):
    created = client.post(
        "/api/contacts/", json=CONTACT_PAYLOAD, headers=auth_headers
    ).json()
    resp = client.delete(f"/api/contacts/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    miss = client.delete(f"/api/contacts/{created['id']}", headers=auth_headers)
    assert miss.status_code == 404


def test_upcoming_birthdays_window(client, auth_headers):
    today = date.today()
    soon = today + timedelta(days=3)
    far = today + timedelta(days=60)

    client.post(
        "/api/contacts/",
        json={**CONTACT_PAYLOAD, "email": "soon@e.com",
              "birthday": f"1990-{soon.month:02d}-{soon.day:02d}"},
        headers=auth_headers,
    )
    client.post(
        "/api/contacts/",
        json={**CONTACT_PAYLOAD, "email": "far@e.com",
              "birthday": f"1990-{far.month:02d}-{far.day:02d}"},
        headers=auth_headers,
    )
    resp = client.get("/api/contacts/upcoming-birthdays?days=7", headers=auth_headers)
    assert resp.status_code == 200
    emails = {c["email"] for c in resp.json()}
    assert "soon@e.com" in emails
    assert "far@e.com" not in emails


def test_root_and_healthz(client):
    assert client.get("/").status_code == 200
    assert client.get("/healthz").json() == {"status": "ok"}
