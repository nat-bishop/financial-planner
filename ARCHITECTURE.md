# Architecture

Personal finance app. Single-user. SQLite database. Syncs from SimpleFIN.

## Request Flow

```
┌─────────┐     ┌─────────┐     ┌──────────────┐     ┌─────────┐
│ Client  │────▶│ FastAPI │────▶│ SimpleFIN    │────▶│ SQLite  │
│         │◀────│ Routes  │◀────│ Client/Sync  │◀────│         │
└─────────┘     └─────────┘     └──────────────┘     └─────────┘
```

1. Routes call SimpleFIN client or database directly (no service layer)
2. Sync fetches accounts/transactions, upserts to preserve user data
3. Analytics queries aggregate stored transactions

## Why No Abstractions

**Direct SimpleFIN client** - No provider interface. Adding Plaid/Yodlee later? Write new clients then. YAGNI.

**Routes call models directly** - At this scale, a service layer adds indirection without benefit. When logic gets complex, extract it.

**SQLite** - Single user, local data. No concurrent write pressure. Async driver (aiosqlite) keeps the API non-blocking.

## Data Model

```
Credential ──── encrypted SimpleFIN access URL
    │
Account ─────── bank account (from SimpleFIN)
    │
    └── Transaction ─── financial transaction
            │
            ├── Core fields (from provider, overwritten on sync)
            │   posted_at, amount, description, is_pending
            │
            └── Enrichment fields (user-managed, preserved on sync)
                category, subcategory, tags, notes

CategoryRule ── auto-categorization patterns (not yet wired up)
SyncLog ─────── audit trail for sync operations
```

## Sync Mechanics

SimpleFIN provides stable transaction IDs. The sync uses SQLite's `INSERT ... ON CONFLICT DO UPDATE` (upsert) with these behaviors:

| Field Type | On Conflict |
|------------|-------------|
| Provider fields | Overwritten |
| User fields (category, tags, notes) | Preserved |
| `updated_at` | Set to now |

Default sync window: 60 days (SimpleFIN's maximum).

## Amounts

All monetary values stored as **integers in cents**. Avoids floating-point rounding issues.

```python
# SimpleFIN sends "123.45" → stored as 12345
# Display: divide by 100
```

## Timestamps

All dates stored as **Unix timestamps** (integers). Simpler than datetime parsing, timezone-agnostic.

## Encryption

SimpleFIN access URLs contain embedded credentials. Stored encrypted with Fernet (symmetric encryption). Key must be set via `ENCRYPTION_KEY` environment variable.

```
app/encryption.py - encrypt()/decrypt() helpers
```

## File Layout

```
app/
├── main.py          # FastAPI app, lifespan hooks
├── config.py        # Settings from environment
├── database.py      # Async engine, session factory
├── models.py        # SQLAlchemy models
├── schemas.py       # Pydantic request/response models
├── encryption.py    # Fernet encrypt/decrypt
├── simplefin.py     # SimpleFIN API client
├── sync.py          # Sync orchestration (upserts)
└── routes/
    ├── health.py       # GET /health
    ├── sync.py         # POST /sync/credentials, POST /sync/
    ├── accounts.py     # GET /accounts
    ├── transactions.py # GET/PATCH /transactions
    └── analytics.py    # GET /analytics/spending-by-category
```
