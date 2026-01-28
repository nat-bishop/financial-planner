from pydantic import BaseModel, ConfigDict


# Credentials
class CredentialCreate(BaseModel):
    setup_token: str  # SimpleFIN setup token to claim


class CredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    created_at: int
    updated_at: int | None


# Accounts
class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    org_domain: str
    org_name: str | None
    name: str
    account_type: str | None
    currency: str
    balance_current: int | None
    balance_available: int | None
    balance_date: int | None
    last_synced_at: int | None
    created_at: int


# Transactions
class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: str
    external_id: str
    posted_at: int
    amount: int
    description: str
    is_pending: bool
    category: str | None
    subcategory: str | None
    tags: str | None
    notes: str | None
    created_at: int
    updated_at: int | None


class TransactionUpdate(BaseModel):
    category: str | None = None
    subcategory: str | None = None
    tags: str | None = None  # JSON array as string
    notes: str | None = None


# Sync
class SyncResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: int
    completed_at: int | None
    status: str
    accounts_synced: int
    transactions_added: int
    transactions_updated: int
    error_message: str | None


# Health
class SyncError(BaseModel):
    at: int
    message: str | None


class HealthResponse(BaseModel):
    status: str
    last_sync_at: int | None
    last_sync_status: str | None
    account_count: int
    recent_errors: list[SyncError]


# Analytics
class SpendingByCategory(BaseModel):
    category: str | None
    total: int  # cents
    count: int


class SpendingByCategoryResponse(BaseModel):
    start_date: int
    end_date: int
    categories: list[SpendingByCategory]
