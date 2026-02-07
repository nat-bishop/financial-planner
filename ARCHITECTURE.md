# Architecture

Personal finance app. Single-user. SQLite database. Syncs from Plaid.

## Request Flow

```
┌─────────┐     ┌─────────┐     ┌──────────────┐     ┌─────────┐
│ Vue SPA │────▶│ FastAPI │────▶│ Plaid SDK    │────▶│ SQLite  │
│         │◀────│ Routes  │◀────│ + Sync Logic │◀────│         │
└─────────┘     └─────────┘     └──────────────┘     └─────────┘
```

1. Routes call Plaid client or database directly (no service layer)
2. Sync fetches accounts/transactions via cursor-based pagination, upserts to preserve user data
3. Analytics queries aggregate stored transactions

## Data Flow: Plaid Sync

```
POST /sync/
  → acquire sync lock (409 if held)
  → load Credential (encrypted access_token + item_id)
  → loop:
      → PlaidClient.sync_transactions(access_token, cursor)
      → upsert accounts
      → upsert added transactions (with Plaid category)
      → upsert modified transactions (preserve user fields)
      → delete removed transactions
      → save cursor checkpoint
      → break if !has_more
  → release lock
  → return SyncLog
```

## Credential Storage

Plaid access tokens are stored encrypted with Fernet symmetric encryption:
```
Credential {
  id: UUID
  provider: "plaid"
  encrypted_data: Fernet(JSON({ access_token, item_id }))
  sync_cursor: string  // Plaid cursor for incremental sync
}
```

## Data Model

```
Credential ──── encrypted Plaid access token + cursor
    │
Account ─────── bank account (from Plaid)
    │           type/subtype: "depository/checking", "credit/credit card"
    │
    └── Transaction ─── financial transaction
            │
            ├── Core fields (from Plaid, overwritten on sync)
            │   posted_at, amount, description, is_pending
            │
            └── Enrichment fields (user-managed, preserved on sync)
                category, subcategory, tags, notes

CategoryRule ── auto-categorization patterns (not yet wired up)
SyncLog ─────── audit trail for sync operations
```

## Sync Mechanics

Plaid provides cursor-based transaction sync. Each sync call returns added, modified, and removed transactions plus a cursor for the next page.

| Field Type | On Conflict |
|------------|-------------|
| Provider fields | Overwritten |
| User fields (category, tags, notes) | Preserved |
| `updated_at` | Set to now |

The cursor is saved after each page for safe checkpointing on partial failures.

## Amounts

All monetary values stored as **integers in cents**. Avoids floating-point rounding issues.

```
Plaid: positive = expense (money out), negative = income (money in)
Ours:  negative = expense, positive = income

Plaid 50.00 (expense)  → stored as -5000
Plaid -1500.00 (income) → stored as 150000
```

## Timestamps

All dates stored as **Unix timestamps** (integers). Simpler than datetime parsing, timezone-agnostic.

## Encryption

Plaid access tokens are stored encrypted with Fernet (symmetric encryption). Key must be set via `ENCRYPTION_KEY` environment variable.

## File Layout

```
app/
├── main.py          # FastAPI app, lifespan hooks, CORS
├── config.py        # Settings from environment
├── database.py      # Async engine, session factory
├── models.py        # SQLAlchemy models
├── schemas.py       # Pydantic request/response models
├── encryption.py    # Fernet encrypt/decrypt
├── plaid.py         # Plaid API client (async wrapper)
├── sync.py          # Sync orchestration (upserts, lock)
└── routes/
    ├── health.py       # GET /health
    ├── sync.py         # Plaid credential + sync endpoints
    ├── accounts.py     # GET /accounts
    ├── transactions.py # GET/PATCH /transactions
    └── analytics.py    # GET /analytics/spending-by-category

frontend/
├── src/
│   ├── views/          # Dashboard, Transactions, Accounts
│   ├── components/     # AccountCard, TransactionTable, SpendingChart, etc.
│   ├── composables/    # useApi (typed fetch wrapper)
│   ├── stores/         # Pinia stores (accounts, transactions, sync)
│   ├── types.ts        # TypeScript interfaces matching backend schemas
│   └── router.ts       # Vue Router config
└── vite.config.ts      # Proxies /api/* to backend
```
