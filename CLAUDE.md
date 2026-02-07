# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Finance Planner is a personal finance application that syncs financial data from Plaid. It provides account management, transaction tracking, and spending analytics with encrypted credential storage.

**Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), SQLite/aiosqlite, Plaid SDK, Pydantic 2.0
**Frontend:** Vue 3 + Vite + TypeScript + Tailwind CSS v4 + Pinia (in `frontend/`)
**Package Managers:** uv (backend), npm (frontend)

## Commands

```bash
# Backend
uv sync                              # Install dependencies
uvicorn app.main:app --reload        # Dev server (port 8000)
pytest                               # Run all tests (34 tests)
pytest tests/test_api.py             # Run one test file
pytest tests/test_api.py::TestSyncEndpoints::test_trigger_sync_409_when_already_running -v  # Single test
ruff check app tests                 # Lint
ruff check app tests --fix           # Auto-fix lint issues
alembic upgrade head                 # Apply migrations
alembic revision --autogenerate -m "description"  # Create migration

# Frontend
cd frontend && npm install           # Install deps
cd frontend && npm run dev           # Dev server (port 5173)
cd frontend && npm run build         # Production build
```

## Architecture

### Core Flow
1. User connects bank via Plaid Link (or `POST /sync/sandbox-token` for testing) → access token + item ID encrypted in Credential table
2. `POST /sync/` triggers cursor-based transaction sync with `asyncio.Lock` mutex (returns 409 if already running)
3. Each sync page: upsert accounts, upsert added/modified transactions, delete removed transactions, checkpoint cursor
4. Upserts preserve user-managed fields (category, tags, notes) while overwriting provider fields (amount, description, is_pending)

### Key Modules
- `app/plaid.py` — Async Plaid client. The plaid-python SDK is synchronous, wrapped with `asyncio.to_thread()`.
- `app/sync.py` — Sync orchestration: cursor pagination loop, upserts via `insert().on_conflict_do_update()`, `_sync_lock` mutex.
- `app/routes/sync.py` — Credential management (create/exchange/delete) and sync trigger endpoint.
- `app/database.py` — Session factory with auto-commit on success, auto-rollback on exception (via `get_db` dependency).
- `app/config.py` — Pydantic settings from `.env`. See `.env.example` for required vars.

### Critical Conventions
- **Amounts in cents** as integers. **Sign convention:** negative = expense, positive = income. This is **inverted from Plaid** (Plaid: positive = expense). Conversion in `_plaid_amount_to_cents()`.
- **Dates** as Unix timestamps (integers).
- **Upsert field split:** On conflict, `posted_at`, `amount`, `description`, `is_pending`, `raw_data` are overwritten. `category`, `subcategory`, `tags`, `notes` are preserved. This is what makes user edits survive re-syncs.
- **Account types** stored as `"type/subtype"` strings (e.g., `"depository/checking"`, `"credit/credit card"`).

### Frontend
- Vite proxies `/api/*` → `http://localhost:8000` (strips `/api` prefix). The `useApi.ts` composable prefixes all fetch calls with `/api`.
- Tailwind CSS **v4** — uses `@import "tailwindcss"` and `@theme {}` blocks in `style.css`, not a v3 tailwind.config.
- Pinia stores in `src/stores/` (accounts, transactions, sync).

## Lint / Testing Notes

- **Ruff** is the linter. B008 is ignored globally (FastAPI `Depends()` in argument defaults). T20 bans `print()` in app code but is allowed in tests.
- **pytest-asyncio** in auto mode — all async test functions auto-detected. Fixtures `db` and `client` are shared via `conftest.py`.
- Tests use in-memory SQLite and mock PlaidClient via `unittest.mock.patch`. Fixtures in `tests/fixtures/` provide Plaid sync response data (initial + incremental).
- The `ENCRYPTION_KEY` env var is set in `conftest.py` before app module imports.

## Configuration

Required env vars (see `.env.example`):
- `ENCRYPTION_KEY` — Fernet key (generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- `PLAID_CLIENT_ID`, `PLAID_SECRET` — From dashboard.plaid.com
- `PLAID_ENVIRONMENT` — `sandbox` (default) | `development` | `production`
- `DATABASE_URL` — Default: `sqlite+aiosqlite:///./data/finance.db`
