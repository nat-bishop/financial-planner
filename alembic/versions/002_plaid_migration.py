"""Plaid migration

Revision ID: 002
Revises: 001
Create Date: 2024-01-15

Adds sync_cursor to credentials for Plaid cursor-based sync.
Makes org_domain nullable since Plaid doesn't provide institution domains.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add sync_cursor for Plaid's cursor-based sync
    op.add_column("credentials", sa.Column("sync_cursor", sa.String(), nullable=True))

    # Make org_domain nullable (Plaid doesn't provide institution domains)
    # SQLite doesn't support ALTER COLUMN, so we use batch_alter_table
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.alter_column(
            "org_domain",
            existing_type=sa.String(),
            nullable=True,
        )


def downgrade() -> None:
    op.drop_column("credentials", "sync_cursor")

    with op.batch_alter_table("accounts") as batch_op:
        batch_op.alter_column(
            "org_domain",
            existing_type=sa.String(),
            nullable=False,
        )
