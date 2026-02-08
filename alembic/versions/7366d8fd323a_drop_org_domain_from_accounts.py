"""drop org_domain from accounts

Revision ID: 7366d8fd323a
Revises: c87ef8f921fd
Create Date: 2026-02-07 18:13:32.340633

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7366d8fd323a'
down_revision: Union[str, None] = 'c87ef8f921fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('accounts', 'org_domain')


def downgrade() -> None:
    op.add_column('accounts', sa.Column('org_domain', sa.String(), nullable=False, server_default=''))
