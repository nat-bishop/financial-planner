"""Add transacted_at column to transactions

Revision ID: 005
Revises: 004
Create Date: 2026-02-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("transacted_at", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "transacted_at")
