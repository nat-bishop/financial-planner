"""Default category to Uncategorized and remove default categories

Revision ID: 004
Revises: 003
Create Date: 2026-02-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Fill NULLs BEFORE making column non-nullable
    op.execute("UPDATE transactions SET category = 'Uncategorized' WHERE category IS NULL")

    # 2. Schema change (batch mode for SQLite)
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.alter_column(
            "category", nullable=False, server_default="Uncategorized"
        )

    # 3. Remove default categories from DB
    op.execute("DELETE FROM categories WHERE is_default = 1")


def downgrade() -> None:
    import time

    # Re-insert 16 defaults
    now = int(time.time())
    categories_table = sa.table(
        "categories",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_default", sa.Boolean),
        sa.column("created_at", sa.Integer),
    )
    defaults = [
        ("Income", "Salary, wages, freelance, refunds, transfers in"),
        ("Housing", "Rent, mortgage, property tax, HOA fees"),
        ("Utilities", "Electric, gas, water, sewer, trash, internet, phone"),
        ("Food & Dining", "Groceries, restaurants, takeout, coffee shops, bars"),
        ("Transportation", "Gas, parking, tolls, public transit, rideshare, car maintenance"),
        ("Shopping", "Clothing, electronics, household items, general retail"),
        ("Health & Medical", "Doctor, dentist, pharmacy, insurance premiums, gym"),
        ("Entertainment", "Streaming, movies, concerts, games, hobbies"),
        ("Personal Care", "Haircuts, cosmetics, spa"),
        ("Education", "Tuition, books, courses, student loans"),
        ("Travel", "Hotels, flights, vacation expenses"),
        ("Insurance", "Auto, home, life, health insurance premiums"),
        ("Subscriptions", "Software, memberships, recurring services"),
        ("Gifts & Donations", "Charity, gifts, tithes"),
        ("Fees & Charges", "Bank fees, ATM fees, late fees, interest charges"),
        ("Transfers", "Account-to-account transfers, payments between own accounts"),
    ]
    op.bulk_insert(
        categories_table,
        [
            {"name": name, "description": desc, "is_default": True, "created_at": now}
            for name, desc in defaults
        ],
    )

    # Revert column to nullable
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.alter_column("category", nullable=True, server_default=None)
