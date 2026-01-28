# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Finance Planner is a personal finance application that syncs financial data from SimpleFIN (a banking data aggregation service). It provides account management, transaction tracking, and spending analytics with encrypted credential storage.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), SQLite with aiosqlite, Alembic migrations, Fernet encryption, httpx, Pydantic 2.0

**Package Manager:** uv

## Commands

```bash
# Install dependencies
uv sync

# Run development server
uvicorn app.main:app --reload

# Run all tests
pytest

# Run specific test file
pytest tests/test_api.py
pytest tests/test_sync.py

# Run with verbose output
pytest -v

# Database migrations
alembic upgrade head              # Apply migrations
alembic downgrade -1              # Revert last migration
alembic revision --autogenerate -m "description"  # Create migration
```

## Architecture

### Core Flow
1. User claims SimpleFIN setup token → encrypted access URL stored in Credential table
2. Sync operation fetches accounts/transactions from SimpleFIN API (60-day window)
3. Data upserted to preserve user-managed fields (category, tags, notes)
4. Analytics computed from stored transactions

### Key Modules
- `app/main.py` - FastAPI app with lifespan management
- `app/simplefin.py` - Async SimpleFIN API client
- `app/sync.py` - Sync orchestration (upserts accounts/transactions)
- `app/encryption.py` - Fernet utilities for credential storage
- `app/routes/` - API endpoints (health, sync, accounts, transactions, analytics)

### Database Models (app/models.py)
- **Credential** - Encrypted SimpleFIN access URLs
- **Account** - Bank accounts with balances and org info
- **Transaction** - Transactions with user-managed enrichment fields
- **CategoryRule** - Pattern-based auto-categorization rules
- **SyncLog** - Audit trail for sync operations

### Key Patterns
- **Async throughout:** All DB operations and HTTP calls use async/await
- **Upserts:** `insert().on_conflict_do_update()` for idempotent syncs
- **Amounts in cents:** All monetary values stored as integers
- **Unix timestamps:** Dates stored as integer timestamps

### API Endpoints
- `GET /health` - Status, last sync, account count
- `POST /sync/credentials` - Claim setup token
- `POST /sync/` - Trigger sync (optional date range)
- `GET /accounts`, `GET /accounts/{id}` - Account data
- `GET /transactions`, `PATCH /transactions/{id}` - Transaction CRUD
- `GET /analytics/spending-by-category` - Spending totals

## Configuration

Required environment variables (see .env.example):
- `DATABASE_URL` - SQLite connection string (default: `sqlite+aiosqlite:///./data/finance.db`)
- `ENCRYPTION_KEY` - Fernet key for credential encryption (generate with `Fernet.generate_key()`)
- `SIMPLEFIN_BASE_URL` - SimpleFIN API URL (default: `https://beta-bridge.simplefin.org`)

## Testing

Tests use in-memory SQLite and mock SimpleFIN responses. Test fixtures in `tests/fixtures/simplefin_response.json` provide realistic API response format.
