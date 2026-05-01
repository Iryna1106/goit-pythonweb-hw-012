"""Unit tests for :mod:`src.repository.contacts`."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.repository import contacts as repo_contacts
from src.schemas.contacts import ContactCreate, ContactUpdate


@pytest.fixture()
def contact_payload() -> ContactCreate:
    return ContactCreate(
        first_name="Ivan",
        last_name="Franko",
        email="ivan.franko@example.com",
        phone="+380501234567",
        birthday=date(1990, 5, 17),
    )


def test_create_contact_persists_owner(db_session, confirmed_user, contact_payload):
    contact = repo_contacts.create_contact(db_session, confirmed_user, contact_payload)
    assert contact.id is not None
    assert contact.user_id == confirmed_user.id
    assert contact.email == "ivan.franko@example.com"


def test_get_contact_returns_owned_record(db_session, confirmed_user, contact_payload):
    created = repo_contacts.create_contact(db_session, confirmed_user, contact_payload)
    got = repo_contacts.get_contact(db_session, confirmed_user, created.id)
    assert got is not None
    assert got.id == created.id


def test_get_contact_isolated_per_user(db_session, user_factory, contact_payload):
    owner = user_factory(username="owner", email="owner@example.com")
    other = user_factory(username="other", email="other@example.com")
    created = repo_contacts.create_contact(db_session, owner, contact_payload)
    assert repo_contacts.get_contact(db_session, other, created.id) is None


def test_get_contact_by_email(db_session, confirmed_user, contact_payload):
    repo_contacts.create_contact(db_session, confirmed_user, contact_payload)
    got = repo_contacts.get_contact_by_email(
        db_session, confirmed_user, contact_payload.email
    )
    assert got is not None
    got_none = repo_contacts.get_contact_by_email(
        db_session, confirmed_user, "missing@example.com"
    )
    assert got_none is None


def test_get_contacts_filters_and_paginates(db_session, confirmed_user):
    base = ContactCreate(
        first_name="A",
        last_name="B",
        email="a@e.com",
        phone="+380501234567",
        birthday=date(1990, 1, 1),
    )
    for i in range(5):
        body = base.model_copy(
            update={
                "first_name": f"First{i}",
                "last_name": f"Last{i}",
                "email": f"a{i}@e.com",
            }
        )
        repo_contacts.create_contact(db_session, confirmed_user, body)

    all_contacts = repo_contacts.get_contacts(db_session, confirmed_user)
    assert len(all_contacts) == 5

    paged = repo_contacts.get_contacts(db_session, confirmed_user, skip=2, limit=2)
    assert len(paged) == 2

    by_first = repo_contacts.get_contacts(db_session, confirmed_user, first_name="First1")
    assert len(by_first) == 1 and by_first[0].first_name == "First1"

    by_last = repo_contacts.get_contacts(db_session, confirmed_user, last_name="Last3")
    assert len(by_last) == 1 and by_last[0].last_name == "Last3"

    by_email = repo_contacts.get_contacts(db_session, confirmed_user, email="a4@e.com")
    assert len(by_email) == 1


def test_update_contact_applies_partial(db_session, confirmed_user, contact_payload):
    created = repo_contacts.create_contact(db_session, confirmed_user, contact_payload)
    out = repo_contacts.update_contact(
        db_session,
        confirmed_user,
        created.id,
        ContactUpdate(phone="+380501112233"),
    )
    assert out is not None
    assert out.phone == "+380501112233"
    assert out.first_name == "Ivan"  # unchanged


def test_update_contact_returns_none_when_missing(db_session, confirmed_user):
    out = repo_contacts.update_contact(
        db_session, confirmed_user, 9999, ContactUpdate(first_name="X")
    )
    assert out is None


def test_delete_contact_removes(db_session, confirmed_user, contact_payload):
    created = repo_contacts.create_contact(db_session, confirmed_user, contact_payload)
    out = repo_contacts.delete_contact(db_session, confirmed_user, created.id)
    assert out is not None
    assert repo_contacts.get_contact(db_session, confirmed_user, created.id) is None


def test_delete_contact_returns_none_when_missing(db_session, confirmed_user):
    assert repo_contacts.delete_contact(db_session, confirmed_user, 9999) is None


def test_upcoming_birthdays_finds_contacts_in_window(db_session, confirmed_user):
    today = date.today()
    in_three = today + timedelta(days=3)
    out_of_window = today + timedelta(days=30)

    repo_contacts.create_contact(
        db_session,
        confirmed_user,
        ContactCreate(
            first_name="Soon",
            last_name="Bday",
            email="soon@e.com",
            phone="+380501234567",
            birthday=date(1990, in_three.month, in_three.day),
        ),
    )
    repo_contacts.create_contact(
        db_session,
        confirmed_user,
        ContactCreate(
            first_name="Far",
            last_name="Bday",
            email="far@e.com",
            phone="+380501234567",
            birthday=date(1990, out_of_window.month, out_of_window.day),
        ),
    )
    res = repo_contacts.get_upcoming_birthdays(db_session, confirmed_user, days=7)
    emails = {c.email for c in res}
    assert "soon@e.com" in emails
    assert "far@e.com" not in emails
