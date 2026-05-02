"""Outbound email helpers.

Currently provides two helpers — :func:`send_verification_email` and
:func:`send_password_reset_email` — that render a Jinja2 HTML template
and dispatch the message via :mod:`fastapi_mail`. Both helpers swallow
:class:`~fastapi_mail.errors.ConnectionErrors` so the surrounding HTTP
flow continues to work in dev environments where SMTP is not configured;
the failure is logged but never propagated.

Templates live in :mod:`src.services.templates`.
"""
from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from fastapi_mail.errors import ConnectionErrors
from pydantic import EmailStr

from src.conf.config import settings
from src.services.auth import create_email_token, create_password_reset_token

conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS,
    TEMPLATE_FOLDER=Path(__file__).parent / "templates",
)
"""Process-wide :mod:`fastapi_mail` connection config built from settings."""


async def send_verification_email(email: EmailStr, username: str, base_url: str) -> None:
    """Send a verification email containing a tokenized confirmation link.

    Args:
        email: Recipient — also embedded in the JWT's ``sub`` claim.
        username: Recipient's display name (used in the greeting line).
        base_url: Public URL of the API; the verification link is
            constructed as ``{base_url}/api/auth/confirmed_email/{token}``.

    Returns:
        None. Errors are logged and swallowed so registration does not
        fail when SMTP is unavailable.
    """
    try:
        token = create_email_token(str(email))
        message = MessageSchema(
            subject="Confirm your email - Contacts API",
            recipients=[email],
            template_body={
                "host": base_url.rstrip("/"),
                "username": username,
                "token": token,
            },
            subtype=MessageType.html,
        )
        fm = FastMail(conf)
        await fm.send_message(message, template_name="verify_email.html")
    except ConnectionErrors as err:
        print(f"[email] failed to send verification email: {err}")


async def send_password_changed_notice(email: EmailStr, username: str, base_url: str) -> None:
    """Notify a user that their password was just changed.

    Sent immediately after a successful ``/reset-password/confirm`` call.
    Lets the legitimate account owner notice unauthorised resets and
    react. Errors are logged and swallowed.

    Args:
        email: Recipient.
        username: Recipient's display name.
        base_url: Public URL of the API; used for the "reset again"
            recovery link in the email body.
    """
    try:
        message = MessageSchema(
            subject="Your password was changed - Contacts API",
            recipients=[email],
            template_body={
                "host": base_url.rstrip("/"),
                "username": username,
            },
            subtype=MessageType.html,
        )
        fm = FastMail(conf)
        await fm.send_message(message, template_name="password_changed_notice.html")
    except ConnectionErrors as err:
        print(f"[email] failed to send password-changed notice: {err}")


async def send_password_reset_email(email: EmailStr, username: str, base_url: str) -> None:
    """Send a password-reset email with a short-lived single-use link.

    The token is single-use — once the recipient confirms a new password,
    its JTI is marked consumed so the link cannot be replayed.

    Args:
        email: Recipient.
        username: Recipient's display name.
        base_url: Public URL of the API; the reset link is constructed
            as ``{base_url}/api/auth/reset-password/{token}``.

    Returns:
        None. Errors are logged and swallowed.
    """
    try:
        token, _jti = create_password_reset_token(str(email))
        message = MessageSchema(
            subject="Reset your password - Contacts API",
            recipients=[email],
            template_body={
                "host": base_url.rstrip("/"),
                "username": username,
                "token": token,
            },
            subtype=MessageType.html,
        )
        fm = FastMail(conf)
        await fm.send_message(message, template_name="reset_password.html")
    except ConnectionErrors as err:
        print(f"[email] failed to send password reset email: {err}")
