"""Database access layer for :class:`~src.database.models.User`.

The functions here form a thin, easily-mocked layer over SQLAlchemy
sessions. Every function takes the :class:`Session` as its first
argument so unit tests can drop in either an in-memory SQLite session
or a :class:`unittest.mock.MagicMock`. Routes never call the ORM
directly — they go through this module.

Responsibilities:

* Lookups by email or username.
* Creating users (with password hashing) — used by registration and by
  fixtures that bootstrap admin accounts.
* Mutating user state (avatar, password, role, email confirmation) and
  invalidating the Redis cache for that user so subsequent requests
  observe the new state.
"""
from datetime import datetime, timezone
from typing import List, Optional

from libgravatar import Gravatar
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import User, UserRole
from src.schemas.users import UserCreate
from src.services import cache as user_cache
from src.services.auth import get_password_hash


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Return the user with the given email, or ``None``.

    Args:
        db: Active SQLAlchemy session.
        email: Email address to look up. Case-sensitive — Pydantic
            validation already normalises emails on input.

    Returns:
        The matching :class:`User` row, or ``None`` if no row matches.
    """
    stmt = select(User).where(User.email == email)
    return db.execute(stmt).scalar_one_or_none()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Return the user with the given username, or ``None``.

    Args:
        db: Active SQLAlchemy session.
        username: Exact username (case-sensitive).

    Returns:
        The matching :class:`User`, or ``None``.
    """
    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()


def list_users(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
    """Return a paginated slice of all users (ordered by id).

    Used by the admin-only ``GET /api/users`` endpoint. Regular users
    cannot reach this function — :func:`~src.services.auth.require_admin`
    gates the route.

    Args:
        db: Active session.
        skip: Number of rows to skip from the start.
        limit: Maximum rows to return (``1 ≤ limit ≤ 500``).

    Returns:
        List of :class:`User` rows.
    """
    stmt = select(User).order_by(User.id).offset(skip).limit(limit)
    return list(db.execute(stmt).scalars().all())


def create_user(db: Session, body: UserCreate, role: UserRole = UserRole.USER) -> User:
    """Create and persist a new user.

    The password is hashed with bcrypt before persistence; the plaintext
    is never stored. The user starts unconfirmed
    (``confirmed=False``) — :func:`confirm_email` flips that flag once
    the verification link is followed. A best-effort Gravatar lookup is
    performed and stored on the row; failures are silently ignored.

    Args:
        db: Active session.
        body: Validated :class:`UserCreate` payload.
        role: Role to assign. Defaults to :attr:`UserRole.USER`; CLI
            tooling or fixtures can pass :attr:`UserRole.ADMIN` to
            bootstrap administrators.

    Returns:
        The persisted :class:`User` (with ``id`` populated).
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
    """Mark the user identified by ``email`` as having confirmed their email.

    Invalidates the cached row so subsequent requests see the updated
    ``confirmed`` flag.

    Args:
        db: Active session.
        email: Email address of the user to confirm.

    Returns:
        The updated :class:`User`, or ``None`` if no such user exists.
    """
    user = get_user_by_email(db, email)
    if user is None:
        return None
    user.confirmed = True
    db.commit()
    db.refresh(user)
    user_cache.invalidate_user(email)
    return user


def update_avatar(db: Session, email: str, url: str) -> Optional[User]:
    """Update the user's avatar URL.

    Args:
        db: Active session.
        email: Email of the user whose avatar is changing.
        url: Public URL of the new avatar (typically Cloudinary).

    Returns:
        The updated :class:`User`, or ``None`` if the user does not exist.
    """
    user = get_user_by_email(db, email)
    if user is None:
        return None
    user.avatar = url
    db.commit()
    db.refresh(user)
    user_cache.invalidate_user(email)
    return user


def update_password(db: Session, email: str, new_password: str) -> Optional[User]:
    """Hash and store a new password for the user identified by ``email``.

    Also bumps :attr:`User.password_changed_at` to ``now``. The auth
    layer rejects any JWT (access or refresh) whose ``iat`` predates
    this timestamp, so previously-issued tokens — including any that
    might have been stolen — are immediately useless.

    The cached user row is invalidated so the new ``password_changed_at``
    becomes visible on the next request.

    Args:
        db: Active session.
        email: Email of the user whose password is changing.
        new_password: Plain-text new password (already validated for
            length by the schema layer).

    Returns:
        The updated :class:`User`, or ``None`` if no user matches.
    """
    user = get_user_by_email(db, email)
    if user is None:
        return None
    user.hashed_password = get_password_hash(new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    user_cache.invalidate_user(email)
    return user


def set_role(db: Session, email: str, role: UserRole) -> Optional[User]:
    """Assign a new role to a user.

    Used by the admin-only role management endpoint. Invalidates the
    cached row so the new role takes effect on the next request.

    Args:
        db: Active session.
        email: Email of the user being promoted/demoted.
        role: New role to apply.

    Returns:
        The updated :class:`User`, or ``None`` if no user matches.
    """
    user = get_user_by_email(db, email)
    if user is None:
        return None
    user.role = role
    db.commit()
    db.refresh(user)
    user_cache.invalidate_user(email)
    return user
