"""HTTP routes for the authentication subsystem (``/api/auth``).

This router orchestrates the full authentication lifecycle:

* :func:`register` — creates a user and dispatches a verification email.
* :func:`login` — exchanges credentials for an access + refresh token pair.
* :func:`refresh` — rotates tokens using a valid refresh token.
* :func:`confirmed_email` — marks a user's email as verified.
* :func:`request_email` — re-sends a verification email.
* :func:`request_password_reset` / :func:`confirm_password_reset` — the
  password-reset flow with **single-use** tokens.

Every endpoint that returns information about a user uses the same
``UserResponse`` schema (which includes ``role``) so the front-end can
react to administrative privileges consistently.
"""
from datetime import datetime, timezone

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
from src.services import cache as user_cache
from src.services.rate_limit import limiter
from src.services.auth import (
    REFRESH_TOKEN_SCOPE,
    RESET_PASSWORD_TOKEN_SCOPE,
    _ensure_token_not_revoked,
    create_access_token,
    create_refresh_token,
    decode_token,
    decode_token_full,
    verify_password,
)
from src.services.email import (
    send_password_changed_notice,
    send_password_reset_email,
    send_verification_email,
)

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
    """Create a new user and dispatch a verification email.

    The endpoint refuses duplicates with **409** on either email or
    username. On success it returns the persisted user (still
    ``confirmed=False``) and queues a verification email so the user
    can activate the account.

    Args:
        body: Validated registration payload.
        background_tasks: FastAPI scheduler used to send the email
            asynchronously (so the HTTP response is not blocked by SMTP).
        request: Active request (used to build the verification link
            base URL when ``APP_BASE_URL`` is not configured).
        db: Database session.

    Returns:
        The newly-created user as :class:`UserResponse`.

    Raises:
        fastapi.HTTPException: 409 ``"User with this email already exists"``
            or ``"User with this username already exists"``.
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
    """Exchange username/email + password for a token pair.

    The form's ``username`` field accepts either the user's email or
    their username — whichever is more convenient for the client.

    Args:
        form: OAuth2 password-flow form (``username``, ``password``).
        db: Database session.

    Returns:
        :class:`TokenResponse` with both ``access_token`` and
        ``refresh_token``.

    Raises:
        fastapi.HTTPException: 401 ``"Invalid credentials"`` for unknown
            user or wrong password; 401 ``"Email not confirmed"`` for
            unverified accounts.
    """
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
    """Rotate the token pair using a valid refresh token.

    Both the access token *and* the refresh token are reissued so the
    refresh window slides forward; the previous refresh token remains
    valid until its ``exp``.

    Args:
        body: Payload containing a valid ``refresh_token``.
        db: Database session.

    Returns:
        A fresh :class:`TokenResponse`.

    Raises:
        fastapi.HTTPException: 401 if the refresh token is invalid,
            expired, has the wrong scope, or refers to a user that no
            longer exists.
    """
    payload = decode_token_full(body.refresh_token, REFRESH_TOKEN_SCOPE)
    email = payload["sub"]
    user = repo_users.get_user_by_email(db, email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _ensure_token_not_revoked(user, payload.get("iat"))
    return TokenResponse(
        access_token=create_access_token(subject=user.email),
        refresh_token=create_refresh_token(subject=user.email),
    )


@router.get("/confirmed_email/{token}")
def confirmed_email(token: str, db: Session = Depends(get_db)):
    """Verify the email-token sent during registration and mark the user as confirmed.

    Idempotent: a second call with the same valid token returns
    ``"Your email is already confirmed"`` rather than an error.

    Args:
        token: The JWT string from the verification link.
        db: Database session.

    Returns:
        ``{"message": "Email successfully confirmed"}`` on first call,
        or ``{"message": "Your email is already confirmed"}`` on
        subsequent calls.

    Raises:
        fastapi.HTTPException: 401 on token decode failure; 400
            ``"Verification error"`` when the user no longer exists.
    """
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
    """Resend the verification email if the address is registered and not yet confirmed.

    Returns the same generic message regardless of whether the email
    matched a real user, so the endpoint cannot be used to enumerate
    registered addresses.

    Args:
        body: Payload with the email to verify.
        background_tasks: Scheduler used to send the email asynchronously.
        request: Active request (used to compute the email link base URL).
        db: Database session.

    Returns:
        Always ``{"message": "If the email is registered, a verification link has been sent"}``.
    """
    user = repo_users.get_user_by_email(db, body.email)
    if user and not user.confirmed:
        base_url = settings.APP_BASE_URL or str(request.base_url)
        background_tasks.add_task(
            send_verification_email, user.email, user.username, base_url
        )
    return {"message": "If the email is registered, a verification link has been sent"}


@router.post("/reset-password")
@limiter.limit("3/hour")
async def request_password_reset(
    request: Request,
    body: RequestEmail,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Start the password-reset flow.

    Returns the same generic message in all cases so callers cannot
    enumerate registered emails. When the email matches a user, a
    short-lived (default 30 min) JWT is generated and emailed to them
    by :func:`~src.services.email.send_password_reset_email`.

    **Rate-limited** to 3 requests per hour per IP to prevent abuse
    (annoyance attacks where someone spams reset emails to a victim).

    Args:
        request: Active request — used by SlowAPI to derive the IP key
            and to build the email-link base URL.
        body: Payload with the email to reset.
        background_tasks: Scheduler used to send the email asynchronously.
        db: Database session.

    Returns:
        Always ``{"message": "If the email is registered, a password reset link has been sent"}``.
    """
    user = repo_users.get_user_by_email(db, body.email)
    if user is not None:
        base_url = settings.APP_BASE_URL or str(request.base_url)
        background_tasks.add_task(
            send_password_reset_email, user.email, user.username, base_url
        )
    return {"message": "If the email is registered, a password reset link has been sent"}


@router.post("/reset-password/confirm", response_model=UserResponse)
def confirm_password_reset(
    body: ResetPasswordConfirm,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    """Set a new password using a valid, **single-use** reset token.

    The token's ``jti`` claim is recorded in Redis the first time it is
    consumed; any subsequent confirmation attempt with the same token
    is rejected with **400** even before the JWT expires. This prevents
    replay if a reset link is leaked or re-clicked.

    On success the user's password is rotated and any cached profile is
    invalidated so the next request loads the fresh row.

    Args:
        body: Payload with the reset ``token`` and the ``new_password``.
        db: Database session.

    Returns:
        The user, as :class:`UserResponse`, with the new password applied.

    Raises:
        fastapi.HTTPException: 401 for invalid/expired token; 400
            ``"Reset token has already been used"`` for replay attempts;
            400 ``"Invalid reset request"`` for missing user.
    """
    payload = decode_token_full(body.token, RESET_PASSWORD_TOKEN_SCOPE)
    email = payload["sub"]
    jti = payload.get("jti")
    exp_ts = payload.get("exp")
    if jti is None or exp_ts is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Compute remaining TTL so the consumed-marker only lives as long as the token would have.
    remaining = int(exp_ts - datetime.now(timezone.utc).timestamp())
    if remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Reset token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user_cache.mark_password_reset_token_used(jti, remaining):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has already been used",
        )

    user = repo_users.update_password(db, email, body.new_password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset request",
        )

    # Notify the user out-of-band so they can detect unauthorised resets.
    base_url = settings.APP_BASE_URL or str(request.base_url)
    background_tasks.add_task(
        send_password_changed_notice, user.email, user.username, base_url
    )
    return user
