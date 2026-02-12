"""Add 2FA fields to sync_log

Revision ID: 008
Revises: 007
Create Date: 2026-02-08

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sync_log", sa.Column("two_fa_status", sa.String(), nullable=True))
    op.add_column("sync_log", sa.Column("two_fa_method", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("sync_log", "two_fa_method")
    op.drop_column("sync_log", "two_fa_status")
