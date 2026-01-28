"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Credentials table
    op.create_table(
        "credentials",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("encrypted_data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider"),
    )

    # Accounts table
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default="simplefin"),
        sa.Column("org_domain", sa.String(), nullable=False),
        sa.Column("org_name", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("account_type", sa.String(), nullable=True),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("balance_current", sa.Integer(), nullable=True),
        sa.Column("balance_available", sa.Integer(), nullable=True),
        sa.Column("balance_date", sa.Integer(), nullable=True),
        sa.Column("last_synced_at", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Transactions table
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("posted_at", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("is_pending", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("subcategory", sa.String(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("raw_data", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "external_id", name="uq_account_external"),
    )
    op.create_index(
        "idx_transactions_account_date", "transactions", ["account_id", "posted_at"]
    )
    op.create_index("idx_transactions_posted", "transactions", ["posted_at"])
    op.create_index("idx_transactions_category", "transactions", ["category"])

    # Category rules table
    op.create_table(
        "category_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("subcategory", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Sync log table
    op.create_table(
        "sync_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("accounts_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "transactions_added", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "transactions_updated", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("sync_log")
    op.drop_table("category_rules")
    op.drop_index("idx_transactions_category", table_name="transactions")
    op.drop_index("idx_transactions_posted", table_name="transactions")
    op.drop_index("idx_transactions_account_date", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("accounts")
    op.drop_table("credentials")
