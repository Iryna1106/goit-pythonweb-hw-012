"""Database access layer for :class:`~src.database.models.User`.

All functions take a SQLAlchemy :class:`~sqlalchemy.orm.Session` so they are
trivially unit-testable with an in-memory SQLite engine or via mocked sessions.
"""
from typing import Optional

from libgravatar import Gravatar
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import User, UserRole
from src.schemas.users import UserCreate
from src.services import cache as user_cache
from src.services.auth import get_password_hash


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Return the user with the given email, or ``None``."""
    stmt = select(User).where(User.email == email)
    return db.execute(stmt).scalar_one_or_none()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Return the user with the given username, or ``None``."""
    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()


def create_user(db: Session, body: UserCreate, role: UserRole = UserRole.USER) -> User:
    """Create and persist a new user.

    Falls back gracefully if Gravatar lookup fails (e.g. offline tests).
    """
    avatar = None
    try:
        avatar = Gravatar(body.email).get_image()
    except Exception:
        avatar = None

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=get_password_hash(body.password),
        avatar=avatar,
        confirmed=False,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def confirm_email(db: Session, email: str) -> Optional[User]:
    """Mark the user identified by ``email`` as confirmed."""
    user = get_user_by_email(db, email)
    if user is None:
        return None
    user.confirmed = True
    db.commit()
    db.refresh(user)
    user_cache.invalidate_user(email)
    return user


def update_avatar(db: Session, email: str, url: str) -> Optional[User]:
    """Update the user's avatar URL and invalidate the cache."""
    user = get_user_by_email(db, email)
    if user is None:
        return None
    user.avatar = url
    db.commit()
    db.refresh(user)
    user_cache.invalidate_user(email)
    return user


def update_password(db: Session, email: str, new_password: str) -> Optional[User]:
    """Hash and store a new password for the user identified by ``email``."""
    user = get_user_by_email(db, email)
    if user is None:
        return None
    user.hashed_password = get_password_hash(new_password)
    db.commit()
    db.refresh(user)
    user_cache.invalidate_user(email)
    return user


def set_role(db: Session, email: str, role: UserRole) -> Optional[User]:
    """Assign ``role`` to the user identified by ``email``."""
    user = get_user_by_email(db, email)
    if user is None:
        return None
    user.role = role
    db.commit()
    db.refresh(user)
    user_cache.invalidate_user(email)
    return user
