"""Add Insurance category

Revision ID: 011
Revises: 010
Create Date: 2026-02-13

"""

import time
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    now = int(time.time())
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO categories (name, description, is_default, exclude_from_totals, created_at) "
            "VALUES (:name, :desc, :is_default, :exclude, :now)"
        ).bindparams(
            name="Insurance",
            desc="Health, auto, home, life, and renters insurance premiums",
            is_default=True,
            exclude=False,
            now=now,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM categories WHERE name = :name AND is_default = 1"
        ).bindparams(name="Insurance")
    )
