"""Add categories table and categorize_confidence column

Revision ID: 002
Revises: 001
Create Date: 2026-02-08

"""

import time
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_CATEGORIES = [
    ("Income", "Salary, wages, freelance, refunds, transfers in"),
    ("Housing", "Rent, mortgage, property tax, HOA fees"),
    ("Utilities", "Electric, gas, water, sewer, trash, internet, phone"),
    ("Food & Dining", "Groceries, restaurants, takeout, coffee shops, bars"),
    (
        "Transportation",
        "Gas, parking, tolls, public transit, rideshare, car maintenance",
    ),
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


def upgrade() -> None:
    # Create categories table
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Seed default categories
    now = int(time.time())
    categories_table = sa.table(
        "categories",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_default", sa.Boolean),
        sa.column("created_at", sa.Integer),
    )
    op.bulk_insert(
        categories_table,
        [
            {
                "name": name,
                "description": desc,
                "is_default": True,
                "created_at": now,
            }
            for name, desc in DEFAULT_CATEGORIES
        ],
    )

    # Add categorize_confidence to transactions
    op.add_column(
        "transactions",
        sa.Column("categorize_confidence", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "categorize_confidence")
    op.drop_table("categories")
