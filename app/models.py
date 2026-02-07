import time

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Credential(Base):
    """Encrypted provider credentials."""

    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, unique=True)  # 'simplefin'
    encrypted_data: Mapped[str] = mapped_column(Text)  # Fernet-encrypted JSON
    sync_cursor: Mapped[str | None] = mapped_column(String, nullable=True)  # Unix timestamp of last sync
    created_at: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))
    updated_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Account(Base):
    """Bank accounts synced from providers."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # Provider's account ID
    provider: Mapped[str] = mapped_column(
        String, default="simplefin"
    )  # 'simplefin', 'manual'
    org_name: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g., "Chase"
    name: Mapped[str] = mapped_column(String)
    account_type: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # credit, checking, etc.
    currency: Mapped[str] = mapped_column(String, default="USD")
    balance_current: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Cents
    balance_available: Mapped[int | None] = mapped_column(Integer, nullable=True)
    balance_date: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # Unix timestamp
    last_synced_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class Transaction(Base):
    """Financial transactions."""

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "external_id", name="uq_account_external"),
        Index("idx_transactions_account_date", "account_id", "posted_at"),
        Index("idx_transactions_posted", "posted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    external_id: Mapped[str] = mapped_column(String)  # Provider's transaction ID

    # Core data (from provider)
    posted_at: Mapped[int] = mapped_column(Integer)  # Unix timestamp
    amount: Mapped[int] = mapped_column(Integer)  # Cents (positive = deposit)
    description: Mapped[str] = mapped_column(String)
    is_pending: Mapped[bool] = mapped_column(Boolean, default=False)

    # Enrichment (app-managed)
    category: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    subcategory: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # Full provider JSON
    created_at: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))
    updated_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    account: Mapped["Account"] = relationship(back_populates="transactions")


class SyncLog(Base):
    """Sync operation history with raw payloads."""

    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[int] = mapped_column(Integer)
    completed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String, default="running"
    )  # running, success, failed
    accounts_synced: Mapped[int] = mapped_column(Integer, default=0)
    transactions_added: Mapped[int] = mapped_column(Integer, default=0)
    transactions_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Sync response summary JSON
