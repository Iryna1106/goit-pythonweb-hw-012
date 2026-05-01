"""add users table and link contacts to users

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("avatar", sa.String(length=500), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_id", "users", ["id"])

    # Drop the global unique constraint on contacts.email — uniqueness is now per-user.
    op.drop_constraint("uq_contacts_email", "contacts", type_="unique")
    op.drop_index("ix_contacts_email", table_name="contacts")

    # Add user_id FK. Since previous data had no owner, we delete pre-existing contacts.
    op.execute("DELETE FROM contacts")
    op.add_column(
        "contacts",
        sa.Column("user_id", sa.Integer(), nullable=False),
    )
    op.create_foreign_key(
        "fk_contacts_user_id",
        "contacts",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_contacts_user_id", "contacts", ["user_id"])
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_unique_constraint(
        "uq_contacts_user_email", "contacts", ["user_id", "email"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_contacts_user_email", "contacts", type_="unique")
    op.drop_index("ix_contacts_email", table_name="contacts")
    op.drop_index("ix_contacts_user_id", table_name="contacts")
    op.drop_constraint("fk_contacts_user_id", "contacts", type_="foreignkey")
    op.drop_column("contacts", "user_id")
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_unique_constraint("uq_contacts_email", "contacts", ["email"])

    op.drop_index("ix_users_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
