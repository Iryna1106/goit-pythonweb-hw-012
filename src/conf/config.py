"""Application settings loaded from environment / ``.env``.

Uses ``pydantic-settings`` so all values can be overridden by environment
variables. Importing :data:`settings` is the canonical way to read config.
"""
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings (singleton via the module-level :data:`settings`)."""

    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/contacts_db"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    @property
    def database_url_normalized(self) -> str:
        """Return ``DATABASE_URL`` with a SQLAlchemy-2-friendly driver prefix.

        Render and Heroku export ``postgres://...`` which SQLAlchemy 2 no longer
        accepts; rewrite it to ``postgresql+psycopg2://...`` transparently.
        """
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            return "postgresql+psycopg2://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg2://" + url[len("postgresql://"):]
        return url

    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_EMAIL_TOKEN_EXPIRE_HOURS: int = 24
    JWT_RESET_PASSWORD_TOKEN_EXPIRE_MINUTES: int = 30

    CORS_ORIGINS: str = "*"

    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS origins as a list (``["*"]`` if wildcard / empty)."""
        if not self.CORS_ORIGINS or self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    MAIL_USERNAME: str = "user@example.com"
    MAIL_PASSWORD: str = "secret"
    MAIL_FROM: str = "user@example.com"
    MAIL_PORT: int = 465
    MAIL_SERVER: str = "smtp.example.com"
    MAIL_FROM_NAME: str = "Contacts API"
    MAIL_STARTTLS: bool = False
    MAIL_SSL_TLS: bool = True
    USE_CREDENTIALS: bool = True
    VALIDATE_CERTS: bool = True

    APP_BASE_URL: str = "http://localhost:8000"

    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_USER_CACHE_TTL_SECONDS: int = 900

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
