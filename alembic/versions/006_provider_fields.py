"""Add provider field to sync_log and session_data to credentials

Revision ID: 006
Revises: 005
Create Date: 2026-02-08

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sync_log",
        sa.Column(
            "provider",
            sa.String(),
            nullable=False,
            server_default="simplefin",
        ),
    )
    op.add_column(
        "credentials",
        sa.Column("session_data", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sync_log", "provider")
    op.drop_column("credentials", "session_data")
