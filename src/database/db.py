"""SQLAlchemy engine, session factory, and FastAPI dependency.

The engine is built once at import time using
:attr:`Settings.database_url_normalized` so platforms that hand out a
``postgres://`` URL (Render, Heroku) work seamlessly with SQLAlchemy 2,
which requires an explicit driver name.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.conf.config import settings


class Base(DeclarativeBase):
    """Declarative base class shared by all ORM models.

    Models inherit from :class:`Base` so that
    :attr:`Base.metadata` carries every table definition for Alembic
    autogeneration and for ``Base.metadata.create_all`` in tests.
    """


engine = create_engine(settings.database_url_normalized, pool_pre_ping=True, future=True)
"""Process-wide SQLAlchemy engine."""

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
"""Session factory used by :func:`get_db` and :func:`session_scope`."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped :class:`Session`.

    The session is closed after the request finishes regardless of
    success or error.

    Yields:
        :class:`Session`: A session bound to :data:`engine`.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager that commits on success and rolls back on exception.

    Useful for one-off scripts or background jobs that don't run inside
    the FastAPI request lifecycle.

    Yields:
        :class:`Session`.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
