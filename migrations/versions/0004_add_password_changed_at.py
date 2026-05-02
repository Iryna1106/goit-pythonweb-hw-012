"""add password_changed_at column to users

Used by the auth layer to invalidate every JWT (access + refresh) issued
before a password reset, by comparing the token's ``iat`` claim to this
timestamp.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-02 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")
