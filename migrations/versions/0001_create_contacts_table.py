"""create contacts table

Revision ID: 0001
Revises:
Create Date: 2026-04-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("first_name", sa.String(length=50), nullable=False),
        sa.Column("last_name", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("birthday", sa.Date(), nullable=False),
        sa.Column("additional_info", sa.String(length=500), nullable=True),
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
        sa.UniqueConstraint("email", name="uq_contacts_email"),
    )
    op.create_index("ix_contacts_first_name", "contacts", ["first_name"])
    op.create_index("ix_contacts_last_name", "contacts", ["last_name"])
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_index("ix_contacts_id", "contacts", ["id"])


def downgrade() -> None:
    op.drop_index("ix_contacts_id", table_name="contacts")
    op.drop_index("ix_contacts_email", table_name="contacts")
    op.drop_index("ix_contacts_last_name", table_name="contacts")
    op.drop_index("ix_contacts_first_name", table_name="contacts")
    op.drop_table("contacts")
