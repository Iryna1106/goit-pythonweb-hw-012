"""Authentication routes: register, login, email confirmation, refresh, password reset."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from src.conf.config import settings
from src.database.db import get_db
from src.repository import users as repo_users
from src.schemas.users import (
    RefreshTokenRequest,
    RequestEmail,
    ResetPasswordConfirm,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from src.services.auth import (
    REFRESH_TOKEN_SCOPE,
    RESET_PASSWORD_TOKEN_SCOPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from src.services.email import send_password_reset_email, send_verification_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    body: UserCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    """Register a new user and dispatch an email-verification message.

    Responds **201** on success, **409** if the email or username is taken.
    """
    if repo_users.get_user_by_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )
    if repo_users.get_user_by_username(db, body.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this username already exists",
        )
    user = repo_users.create_user(db, body)

    base_url = settings.APP_BASE_URL or str(request.base_url)
    background_tasks.add_task(
        send_verification_email, user.email, user.username, base_url
    )
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Exchange a username/email + password for an ``access_token`` and ``refresh_token``."""
    # form.username may carry either a username or an email.
    user = repo_users.get_user_by_email(db, form.username) or repo_users.get_user_by_username(
        db, form.username
    )
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.confirmed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not confirmed",
        )
    access_token = create_access_token(subject=user.email)
    refresh_token = create_refresh_token(subject=user.email)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Mint a new access token (and rotate the refresh token) given a valid refresh token."""
    email = decode_token(body.refresh_token, REFRESH_TOKEN_SCOPE)
    user = repo_users.get_user_by_email(db, email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(subject=user.email),
        refresh_token=create_refresh_token(subject=user.email),
    )


@router.get("/confirmed_email/{token}")
def confirmed_email(token: str, db: Session = Depends(get_db)):
    """Verify the email-token sent during registration and mark the user as confirmed."""
    email = decode_token(token, "email_token")
    user = repo_users.get_user_by_email(db, email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Verification error"
        )
    if user.confirmed:
        return {"message": "Your email is already confirmed"}
    repo_users.confirm_email(db, email)
    return {"message": "Email successfully confirmed"}


@router.post("/request_email")
async def request_email(
    body: RequestEmail,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    """Resend the verification email if the address is registered and not yet confirmed."""
    user = repo_users.get_user_by_email(db, body.email)
    if user and not user.confirmed:
        base_url = settings.APP_BASE_URL or str(request.base_url)
        background_tasks.add_task(
            send_verification_email, user.email, user.username, base_url
        )
    # Always return the same message so we don't leak whether an email is registered.
    return {"message": "If the email is registered, a verification link has been sent"}


@router.post("/reset-password")
async def request_password_reset(
    body: RequestEmail,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    """Start the password-reset flow.

    Always returns the same message so the endpoint cannot be used to
    enumerate registered emails.
    """
    user = repo_users.get_user_by_email(db, body.email)
    if user is not None:
        base_url = settings.APP_BASE_URL or str(request.base_url)
        background_tasks.add_task(
            send_password_reset_email, user.email, user.username, base_url
        )
    return {"message": "If the email is registered, a password reset link has been sent"}


@router.post("/reset-password/confirm", response_model=UserResponse)
def confirm_password_reset(body: ResetPasswordConfirm, db: Session = Depends(get_db)):
    """Set a new password using a valid reset-password token."""
    email = decode_token(body.token, RESET_PASSWORD_TOKEN_SCOPE)
    user = repo_users.update_password(db, email, body.new_password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset request",
        )
    return user
