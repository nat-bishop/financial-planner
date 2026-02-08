from pydantic import BaseModel, ConfigDict, Field


# Credentials
class CredentialCreate(BaseModel):
    setup_token: str  # SimpleFIN setup token from bridge.simplefin.org


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
    org_name: str | None
    name: str
    account_type: str | None
    currency: str
    balance_current: int | None
    balance_available: int | None
    balance_date: int | None
    last_synced_at: int | None
    created_at: int
    is_disabled: bool


class AccountUpdate(BaseModel):
    is_disabled: bool | None = None


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
    category: str
    subcategory: str | None
    categorize_confidence: float | None
    tags: str | None
    notes: str | None
    created_at: int
    updated_at: int | None


class TransactionListResponse(BaseModel):
    transactions: list[TransactionResponse]
    total_count: int
    total_income: int
    total_expenses: int


class TransactionIdsResponse(BaseModel):
    ids: list[int]


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
    has_credentials: bool
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


# Categories
class CategoryCreate(BaseModel):
    name: str
    description: str | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    is_default: bool
    created_at: int


# LLM / Categorization
class CategorizeRequest(BaseModel):
    transaction_ids: list[int] | None = None


class TransactionCategorization(BaseModel):
    """LLM response for a single transaction."""

    id: int
    category: str
    subcategory: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class BatchCategorizationResponse(BaseModel):
    """LLM response for a batch."""

    transactions: list[TransactionCategorization]


class CategorizeResult(BaseModel):
    transaction_id: int
    description: str
    category: str
    suggested_category: str
    subcategory: str | None
    confidence: float
    reasoning: str
    applied: bool


class CategorizeResponse(BaseModel):
    total_processed: int
    categorized: int
    unable_to_categorize: int
    results: list[CategorizeResult]
    error: str | None = None


class LLMStatusResponse(BaseModel):
    configured: bool
    model: str


