"""Outbound email helpers (verification + password reset).

Both helpers swallow :class:`ConnectionErrors` so that registration / reset
flows continue to work in dev environments where SMTP is not configured.
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


async def send_verification_email(email: EmailStr, username: str, base_url: str) -> None:
    """Send a verification email containing a tokenized confirmation link."""
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
        # Do not crash registration if SMTP isn't configured in dev — just log.
        print(f"[email] failed to send verification email: {err}")


async def send_password_reset_email(email: EmailStr, username: str, base_url: str) -> None:
    """Send a password-reset email with a short-lived tokenized link."""
    try:
        token = create_password_reset_token(str(email))
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
