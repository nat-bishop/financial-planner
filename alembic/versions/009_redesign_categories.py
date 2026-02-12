"""Redesign categories: add exclude_from_totals, remove subcategory, reseed defaults

Revision ID: 009
Revises: 008
Create Date: 2026-02-11

"""

import time
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# New 14-category default set
NEW_CATEGORIES = [
    ("Income", "Salary, wages, interest, dividends, refunds", False),
    ("Housing", "Rent, mortgage, property tax, HOA, renters insurance", False),
    ("Utilities", "Electric, water, gas, internet, phone, trash", False),
    ("Groceries", "Supermarkets, specialty food markets, online grocery", False),
    ("Dining & Drinks", "Restaurants, coffee, bars, fast food, takeout, delivery, bakeries", False),
    ("Transportation", "Gas, rideshare, public transit, parking, car maintenance, auto insurance", False),
    ("Shopping", "Clothing, electronics, household, online retail, pets, general retail", False),
    ("Health & Medical", "Doctor, dentist, pharmacy, health insurance, gym, personal care", False),
    ("Entertainment", "Movies, concerts, events, sports, streaming, hobbies", False),
    ("Education", "Student loans, tuition, books, courses", False),
    ("Travel", "Flights, hotels, vacation expenses", False),
    ("Gifts & Donations", "Charity, gifts, tithes", False),
    ("Fees & Charges", "Bank fees, ATM fees, late fees, interest charges", False),
    ("Transfers", "Internal account transfers, credit card payments", True),
]

# Original 16 categories for downgrade
OLD_CATEGORIES = [
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


def upgrade() -> None:
    # Add exclude_from_totals to categories
    op.add_column(
        "categories",
        sa.Column("exclude_from_totals", sa.Boolean(), nullable=False, server_default="0"),
    )

    # Drop subcategory columns
    op.drop_column("transactions", "subcategory")
    op.drop_column("category_memory", "subcategory")

    # Replace default categories
    op.execute("DELETE FROM categories WHERE is_default = 1")

    now = int(time.time())
    categories_table = sa.table(
        "categories",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_default", sa.Boolean),
        sa.column("exclude_from_totals", sa.Boolean),
        sa.column("created_at", sa.Integer),
    )
    op.bulk_insert(
        categories_table,
        [
            {
                "name": name,
                "description": desc,
                "is_default": True,
                "exclude_from_totals": exclude,
                "created_at": now,
            }
            for name, desc, exclude in NEW_CATEGORIES
        ],
    )


def downgrade() -> None:
    # Re-add subcategory columns
    op.add_column(
        "transactions",
        sa.Column("subcategory", sa.String(), nullable=True),
    )
    op.add_column(
        "category_memory",
        sa.Column("subcategory", sa.String(), nullable=True),
    )

    # Replace categories with original defaults
    op.execute("DELETE FROM categories WHERE is_default = 1")

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
            for name, desc in OLD_CATEGORIES
        ],
    )

    # Drop exclude_from_totals
    op.drop_column("categories", "exclude_from_totals")
