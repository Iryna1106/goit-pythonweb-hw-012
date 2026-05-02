"""User profile + administration routes (``/api/users``).

This router exposes:

* :func:`me` — the rate-limited profile endpoint accessible to any
  authenticated user.
* :func:`update_avatar` — admin-only Cloudinary upload that replaces
  the user's avatar URL. Regular users keep their default Gravatar.
* :func:`list_users` — admin-only paginated user list.
* :func:`update_user_role` — admin-only role change.

Admin-only routes use :func:`~src.services.auth.require_admin` as a
FastAPI dependency, which itself depends on
:func:`~src.services.auth.get_current_user` — so failure to authenticate
returns 401 and a successful authentication that lacks the admin role
returns 403.
"""
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from src.database.db import get_db
from src.database.models import User
from src.repository import users as repo_users
from src.schemas.users import UserResponse, UserRoleUpdate
from src.services.auth import get_current_user, require_admin
from src.services.rate_limit import limiter
from src.services.upload_file import UploadFileService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
@limiter.limit("5/minute")
def me(request: Request, current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile.

    Rate-limited to 5 requests per minute per IP via SlowAPI; bursts
    receive a 429 response with a JSON ``detail``.

    Args:
        request: Active request — required by ``slowapi`` to derive the
            client key from ``X-Forwarded-For`` / remote address.
        current_user: User resolved by :func:`get_current_user`.

    Returns:
        :class:`UserResponse`.
    """
    return current_user


@router.patch("/avatar", response_model=UserResponse)
def update_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Upload a new avatar to Cloudinary and persist the URL on the user row.

    **Admin only.** Regular users keep their default Gravatar so the
    application's default-avatar policy is centrally controlled.

    Args:
        file: ``multipart/form-data`` upload field.
        current_user: User resolved by :func:`require_admin` — guaranteed
            to be :attr:`UserRole.ADMIN`.
        db: Database session.

    Returns:
        Updated :class:`UserResponse` with the new ``avatar`` URL.
    """
    avatar_url = UploadFileService().upload_avatar(file.file, current_user.username)
    user = repo_users.update_avatar(db, current_user.email, avatar_url)
    return user


@router.get("/", response_model=List[UserResponse])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List users (admin-only).

    Args:
        skip: Pagination offset.
        limit: Page size (max 500).
        _admin: Admin enforcement dependency (unused — present only to
            gate the route).
        db: Database session.

    Returns:
        List of :class:`UserResponse`.
    """
    return repo_users.list_users(db, skip=skip, limit=limit)


@router.patch("/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int,
    body: UserRoleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Promote or demote a user (admin-only).

    Includes a self-protection: an admin cannot demote *themselves*
    away from the admin role through this endpoint, to avoid locking
    everyone out of administrative access.

    Args:
        user_id: Primary key of the user to mutate.
        body: New role.
        admin: The admin performing the action (resolved by
            :func:`require_admin`).
        db: Database session.

    Returns:
        Updated :class:`UserResponse`.

    Raises:
        fastapi.HTTPException: 404 if the user is not found; 400 if an
            admin tries to demote themselves.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.id == admin.id and body.role != admin.role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot change their own role",
        )
    return repo_users.set_role(db, target.email, body.role)
