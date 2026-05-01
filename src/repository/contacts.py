"""Database access layer for :class:`~src.database.models.Contact`.

All queries are scoped to the owning :class:`User` so users can only see and
mutate their own contacts.
"""
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import extract, or_, select
from sqlalchemy.orm import Session

from src.database.models import Contact, User
from src.schemas.contacts import ContactCreate, ContactUpdate


def get_contacts(
    db: Session,
    user: User,
    skip: int = 0,
    limit: int = 100,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    email: Optional[str] = None,
) -> List[Contact]:
    """Return paginated contacts for ``user`` with optional ``ilike`` filters."""
    stmt = select(Contact).where(Contact.user_id == user.id)
    if first_name:
        stmt = stmt.where(Contact.first_name.ilike(f"%{first_name}%"))
    if last_name:
        stmt = stmt.where(Contact.last_name.ilike(f"%{last_name}%"))
    if email:
        stmt = stmt.where(Contact.email.ilike(f"%{email}%"))
    stmt = stmt.order_by(Contact.id).offset(skip).limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_contact(db: Session, user: User, contact_id: int) -> Optional[Contact]:
    """Return ``user``'s contact identified by ``contact_id`` or ``None``."""
    stmt = select(Contact).where(Contact.id == contact_id, Contact.user_id == user.id)
    return db.execute(stmt).scalar_one_or_none()


def get_contact_by_email(db: Session, user: User, email: str) -> Optional[Contact]:
    """Look up one of ``user``'s contacts by email or return ``None``."""
    stmt = select(Contact).where(Contact.email == email, Contact.user_id == user.id)
    return db.execute(stmt).scalar_one_or_none()


def create_contact(db: Session, user: User, body: ContactCreate) -> Contact:
    """Persist a new contact owned by ``user``."""
    contact = Contact(**body.model_dump(), user_id=user.id)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def update_contact(
    db: Session, user: User, contact_id: int, body: ContactUpdate
) -> Optional[Contact]:
    """Apply a partial update to ``contact_id`` (must be owned by ``user``)."""
    contact = get_contact(db, user, contact_id)
    if contact is None:
        return None
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return contact


def delete_contact(db: Session, user: User, contact_id: int) -> Optional[Contact]:
    """Delete and return the contact, or ``None`` if it does not belong to ``user``."""
    contact = get_contact(db, user, contact_id)
    if contact is None:
        return None
    db.delete(contact)
    db.commit()
    return contact


def get_upcoming_birthdays(db: Session, user: User, days: int = 7) -> List[Contact]:
    """Return contacts whose birthday (ignoring year) falls within the next ``days`` days.

    Handles year boundaries (e.g. today=Dec 28, window crosses into January).
    """
    today = date.today()
    end = today + timedelta(days=days)

    today_md = (today.month, today.day)
    end_md = (end.month, end.day)

    month = extract("month", Contact.birthday)
    day = extract("day", Contact.birthday)

    if today_md <= end_md:
        condition = or_(
            (month > today_md[0]) & (month < end_md[0]),
            (month == today_md[0]) & (day >= today_md[1]) & (month < end_md[0]),
            (month == end_md[0]) & (day <= end_md[1]) & (month > today_md[0]),
            (month == today_md[0]) & (month == end_md[0]) & (day >= today_md[1]) & (day <= end_md[1]),
        )
    else:
        condition = or_(
            (month > today_md[0]),
            (month == today_md[0]) & (day >= today_md[1]),
            (month < end_md[0]),
            (month == end_md[0]) & (day <= end_md[1]),
        )

    stmt = (
        select(Contact)
        .where(Contact.user_id == user.id)
        .where(condition)
        .order_by(month, day)
    )
    contacts = list(db.execute(stmt).scalars().all())

    def in_window(bd: date) -> bool:
        bd_md = (bd.month, bd.day)
        if today_md <= end_md:
            return today_md <= bd_md <= end_md
        return bd_md >= today_md or bd_md <= end_md

    return [c for c in contacts if in_window(c.birthday)]
