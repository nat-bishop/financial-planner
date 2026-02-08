"""add sync_cursor to credentials

Revision ID: c87ef8f921fd
Revises: 001
Create Date: 2026-02-07 17:15:37.019429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c87ef8f921fd'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('credentials', sa.Column('sync_cursor', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('credentials', 'sync_cursor')
