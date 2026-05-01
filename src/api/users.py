"""User profile routes (``/api/users``)."""
from fastapi import APIRouter, Depends, File, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.database.db import get_db
from src.database.models import User
from src.repository import users as repo_users
from src.schemas.users import UserResponse
from src.services.auth import get_current_user, require_admin
from src.services.upload_file import UploadFileService

router = APIRouter(prefix="/users", tags=["users"])

limiter = Limiter(key_func=get_remote_address)


@router.get("/me", response_model=UserResponse)
@limiter.limit("5/minute")
def me(request: Request, current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile (rate-limited to 5/minute)."""
    return current_user


@router.patch("/avatar", response_model=UserResponse)
def update_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Upload a new avatar to Cloudinary and persist the URL.

    Restricted to admins — regular users keep their default Gravatar.
    """
    avatar_url = UploadFileService().upload_avatar(file.file, current_user.username)
    user = repo_users.update_avatar(db, current_user.email, avatar_url)
    return user
