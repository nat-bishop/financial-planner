# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Finance Planner is a personal finance application that syncs financial data from SimpleFIN Bridge. It provides account management, transaction tracking, and spending analytics with encrypted credential storage.

**Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), SQLite/aiosqlite, httpx, Pydantic 2.0
**Frontend:** Vue 3 + Vite + TypeScript + Tailwind CSS v4 + Pinia (in `frontend/`)
**Package Managers:** uv (backend), npm (frontend)

## Commands

```bash
# Docker workflow (primary)
make start                           # Build & start backend + frontend containers
make stop                            # Stop all services
make logs                            # Tail service logs
make restart                         # Stop + start

# Local workflow (no Docker)
make dev                             # Migrate + start backend & frontend locally
make migrate                         # Apply migrations locally
uv sync                              # Install backend dependencies
cd frontend && npm install           # Install frontend dependencies

# Testing & linting
make test                            # Run all tests (or: pytest)
make lint                            # Lint (or: ruff check app tests)
pytest tests/test_api.py -v          # Run one test file
ruff check app tests --fix           # Auto-fix lint issues

# Migrations
alembic revision --autogenerate -m "description"  # Create migration
```

## Architecture

### Core Flow
1. User gets a setup token from [bridge.simplefin.org](https://bridge.simplefin.org), pastes it in the UI
2. `POST /sync/credentials` claims the one-time token → stores encrypted access URL in Credential table
3. `POST /sync/` fetches accounts + transactions for date range (cursor = last sync timestamp, 60-day max window)
4. Upserts preserve user-managed fields (category, tags, notes) while overwriting provider fields (amount, description, is_pending)
5. Rate limited: minimum 1-hour interval between syncs (~24 requests/day matches SimpleFIN quota). Returns 429 if too soon.

### Key Modules
- `app/simplefin.py` — Async SimpleFIN Bridge client using `httpx.AsyncClient`. Dataclasses: `SFAccount`, `SFTransaction`, `SFSyncResponse`. Amount parsing via `decimal.Decimal` for precision.
- `app/sync.py` — Sync orchestration: date-range query, upserts via `insert().on_conflict_do_update()`, `_sync_lock` mutex, rate limit enforcement.
- `app/routes/sync.py` — Credential management (claim setup token / delete) and sync trigger endpoint.
- `app/database.py` — Session factory with auto-commit on success, auto-rollback on exception (via `get_db` dependency).
- `app/config.py` — Pydantic settings from `.env`. See `.env.example` for required vars.

### Critical Conventions
- **Amounts in cents** as integers. **Sign convention:** negative = expense, positive = income. **Matches SimpleFIN** (no sign inversion needed). Conversion in `_sfin_amount_to_cents()`.
- **Dates** as Unix timestamps (integers). SimpleFIN uses Unix timestamps natively. Pending transactions have `posted=0`, substituted with current timestamp.
- **Upsert field split:** On conflict, `posted_at`, `amount`, `description`, `is_pending`, `raw_data` are overwritten. `category`, `subcategory`, `tags`, `notes` are preserved. This is what makes user edits survive re-syncs.
- **No transaction removal:** SimpleFIN doesn't report removed transactions (unlike Plaid's cursor-based sync).
- **Setup tokens are one-time use.** A 403 on claim means the token was already used — get a new one.

### Frontend
- Vite proxies `/api/*` → `http://localhost:8000` (strips `/api` prefix). The `useApi.ts` composable prefixes all fetch calls with `/api`.
- Tailwind CSS **v4** — uses `@import "tailwindcss"` and `@theme {}` blocks in `style.css`, not a v3 tailwind.config.
- Pinia stores in `src/stores/` (accounts, transactions, sync).
- **SimpleFIN connect flow:** User pastes setup token in text input → `sync.ts:claimSetupToken()` → POST `/sync/credentials` → auto-triggers sync. No SDK or CDN needed.

## Lint / Testing Notes

- **Ruff** is the linter. B008 is ignored globally (FastAPI `Depends()` in argument defaults). T20 bans `print()` in app code but is allowed in tests.
- **pytest-asyncio** in auto mode — all async test functions auto-detected. Fixtures `db` and `client` are shared via `conftest.py`.
- Tests use in-memory SQLite and mock `SimpleFINClient` via `unittest.mock.patch`. Fixtures in `tests/fixtures/` provide SimpleFIN response data (initial + incremental).
- The `ENCRYPTION_KEY` env var is set in `conftest.py` before app module imports.
- Tests that need multiple syncs patch `MIN_SYNC_INTERVAL` to 0 to bypass rate limiting.

## Configuration

Required env vars (see `.env.example`):
- `ENCRYPTION_KEY` — Fernet key (generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- `DATABASE_URL` — Default: `sqlite+aiosqlite:///./data/finance.db`
- `BACKEND_PORT` — Default: `8000`. Used by Docker Compose for port mapping.
- `FRONTEND_PORT` — Default: `5173`. Used by Docker Compose for port mapping.

SimpleFIN needs no env vars — the setup token is provided via the UI.
