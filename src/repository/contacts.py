"""Database access layer for :class:`~src.database.models.Contact`.

Every query is scoped to the owning :class:`User` so users can only
read or mutate their own contacts. The :class:`User` is passed as an
explicit parameter (not derived from a global) so this module remains
trivially unit-testable without a FastAPI request context.

The module covers the full CRUD surface plus an upcoming-birthdays
helper that handles the year-end wrap-around correctly (e.g. today is
Dec 28 and the window crosses into January).
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
    """Return a paginated list of ``user``'s contacts with optional partial filters.

    Args:
        db: Active session.
        user: Owner — only contacts whose ``user_id`` matches are returned.
        skip: Pagination offset.
        limit: Maximum rows to return.
        first_name: Optional case-insensitive substring filter on
            :attr:`Contact.first_name`.
        last_name: Optional case-insensitive substring filter on
            :attr:`Contact.last_name`.
        email: Optional case-insensitive substring filter on
            :attr:`Contact.email`.

    Returns:
        Matching :class:`Contact` rows ordered by ``id``.
    """
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
    """Return ``user``'s contact identified by ``contact_id`` or ``None``.

    Args:
        db: Active session.
        user: Owner.
        contact_id: Primary key of the contact.

    Returns:
        The :class:`Contact`, or ``None`` if it doesn't exist or belongs
        to a different user (the function does not distinguish between
        these two cases — both are treated as "not found" to avoid
        leaking other users' contact ids).
    """
    stmt = select(Contact).where(Contact.id == contact_id, Contact.user_id == user.id)
    return db.execute(stmt).scalar_one_or_none()


def get_contact_by_email(db: Session, user: User, email: str) -> Optional[Contact]:
    """Look up one of ``user``'s contacts by exact email.

    Used by routes to enforce per-user uniqueness on contact emails
    (different users may both store the same external email).

    Args:
        db: Active session.
        user: Owner.
        email: Exact email to match.

    Returns:
        The matching :class:`Contact` or ``None``.
    """
    stmt = select(Contact).where(Contact.email == email, Contact.user_id == user.id)
    return db.execute(stmt).scalar_one_or_none()


def create_contact(db: Session, user: User, body: ContactCreate) -> Contact:
    """Persist a new contact owned by ``user``.

    Args:
        db: Active session.
        user: Owner — :attr:`Contact.user_id` is set automatically.
        body: Validated :class:`ContactCreate` payload.

    Returns:
        The newly persisted :class:`Contact`.
    """
    contact = Contact(**body.model_dump(), user_id=user.id)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def update_contact(
    db: Session, user: User, contact_id: int, body: ContactUpdate
) -> Optional[Contact]:
    """Apply a partial update to one of ``user``'s contacts.

    Only fields present in ``body`` (i.e. ``model_dump(exclude_unset=True)``)
    are written, preserving any unset values.

    Args:
        db: Active session.
        user: Owner.
        contact_id: Primary key of the contact to update.
        body: Partial update payload.

    Returns:
        The updated :class:`Contact`, or ``None`` if it doesn't exist
        or belongs to a different user.
    """
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
    """Delete and return the contact, or ``None`` if it does not belong to ``user``.

    Args:
        db: Active session.
        user: Owner.
        contact_id: Primary key of the contact to remove.

    Returns:
        The deleted :class:`Contact` (already detached) so callers can
        echo it back to the client, or ``None`` if no row matched.
    """
    contact = get_contact(db, user, contact_id)
    if contact is None:
        return None
    db.delete(contact)
    db.commit()
    return contact


def get_upcoming_birthdays(db: Session, user: User, days: int = 7) -> List[Contact]:
    """Return contacts whose birthday (ignoring year) falls within the next ``days`` days.

    The implementation does the heavy filtering at the database level
    using ``EXTRACT(month/day from birthday)`` and then refines the
    result in Python to handle the case where the window crosses the
    year boundary (e.g. today=Dec 28, ``days=10`` ⇒ window ends Jan 7).

    Args:
        db: Active session.
        user: Owner.
        days: Size of the lookahead window in days. Defaults to 7.

    Returns:
        :class:`Contact` rows with birthdays inside the window, ordered
        by month and day.
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
