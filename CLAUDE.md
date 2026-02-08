# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Finance Planner is a personal finance application that syncs financial data from SimpleFIN Bridge. It provides account management, transaction tracking, and spending analytics with encrypted credential storage.

**Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), SQLite/aiosqlite, httpx, Pydantic 2.0, google-genai (Gemini)
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

### Layered Architecture

```
app/
├── main.py                    # App assembly
├── models.py                  # SQLAlchemy models (Credential, Account, Transaction, SyncLog, Category)
├── schemas.py                 # Pydantic schemas
├── core/                      # Shared infrastructure
│   ├── config.py              # Pydantic settings from .env
│   ├── database.py            # Session factory (get_db dependency)
│   └── encryption.py          # Fernet encrypt/decrypt
├── clients/                   # External API clients (pure HTTP, no DB)
│   ├── simplefin.py           # SimpleFIN Bridge client (httpx)
│   └── gemini.py              # Gemini structured output client (google-genai)
├── services/                  # Business logic (orchestration, DB writes)
│   ├── sync.py                # SimpleFIN sync orchestration
│   └── categorize.py          # Batch transaction categorization
├── routes/                    # Thin HTTP handlers
│   ├── accounts.py, analytics.py, health.py, sync.py, transactions.py
│   ├── categories.py          # Category CRUD
│   └── llm.py                 # LLM status, categorize, chat endpoints
```

**Layer rules:** `core/` = infrastructure, `clients/` = pure HTTP (no DB), `services/` = business logic, `routes/` = thin handlers.

### Key Modules
- `app/clients/simplefin.py` — Async SimpleFIN Bridge client using `httpx.AsyncClient`. Dataclasses: `SFAccount`, `SFTransaction`, `SFSyncResponse`. Amount parsing via `decimal.Decimal` for precision.
- `app/clients/gemini.py` — Gemini client with `generate()`, `generate_structured()` (Pydantic response_schema + retry), `stream()`. Singleton via `get_gemini_client()`.
- `app/services/sync.py` — Sync orchestration: date-range query, upserts via `insert().on_conflict_do_update()`, `_sync_lock` mutex, rate limit enforcement.
- `app/services/categorize.py` — Batch categorization: builds prompt from Category table, calls Gemini structured output, applies confidence threshold.
- `app/routes/llm.py` — `GET /llm/status`, `POST /llm/categorize`, `POST /llm/chat` (SSE streaming).
- `app/routes/categories.py` — Category CRUD. DELETE nullifies transactions with that category.
- `app/core/database.py` — Session factory with auto-commit on success, auto-rollback on exception (via `get_db` dependency).
- `app/core/config.py` — Pydantic settings from `.env`. See `.env.example` for required vars.

### Critical Conventions
- **Amounts in cents** as integers. **Sign convention:** negative = expense, positive = income. **Matches SimpleFIN** (no sign inversion needed). Conversion in `_sfin_amount_to_cents()`.
- **Dates** as Unix timestamps (integers). SimpleFIN uses Unix timestamps natively. Pending transactions have `posted=0`, substituted with current timestamp.
- **Upsert field split:** On conflict, `posted_at`, `amount`, `description`, `is_pending`, `raw_data` are overwritten. `category`, `subcategory`, `tags`, `notes` are preserved. This is what makes user edits survive re-syncs.
- **No transaction removal:** SimpleFIN doesn't report removed transactions.
- **Setup tokens are one-time use.** A 403 on claim means the token was already used — get a new one.
- **Category states:** `category IS NULL` = uncategorized (never attempted). `category = "Unable to Categorize"` + `categorize_confidence IS NOT NULL` = LLM tried, below threshold. `category = "Food & Dining"` + `categorize_confidence = 0.92` = LLM categorized. `category = "Food & Dining"` + `categorize_confidence IS NULL` = user manually set.
- **Confidence threshold** is evaluated only at categorize time. Changing `CATEGORIZE_CONFIDENCE_THRESHOLD` does NOT retroactively change existing categorizations.

### Frontend
- Vite proxies `/api/*` → backend (strips `/api` prefix). Default target `http://localhost:8000` for local dev; Docker sets `VITE_API_URL=http://backend:<port>` via compose environment.
- The `useApi.ts` composable prefixes all fetch calls with `/api`.
- Tailwind CSS **v4** — uses `@import "tailwindcss"` and `@theme {}` blocks in `style.css`, not a v3 tailwind.config.
- Pinia stores in `src/stores/` (accounts, transactions, sync, categories, llm).
- **SimpleFIN connect flow:** User pastes setup token in text input → `sync.ts:claimSetupToken()` → POST `/sync/credentials` → auto-triggers sync. No SDK or CDN needed.

### Docker & Infrastructure
- **Primary workflow:** `make start` / `make stop`. Runs via Docker Compose.
- **Port configuration:** `BACKEND_PORT` and `FRONTEND_PORT` in `.env`, referenced in `docker-compose.yml` via `${VAR:-default}` interpolation.
- **Health check:** Backend exposes `GET /health` (queries DB). Docker Compose uses it with `condition: service_healthy` so frontend waits for backend readiness.
- **Hot reload:** Source volumes mounted (`./app`, `./frontend/src`) for live reload in containers.
- **Data persistence:** `db-data` Docker volume stores SQLite database across restarts.
- **Local fallback:** `make dev` runs both servers directly (no Docker). Uses `trap 'kill 0' EXIT` for cleanup.

## Migrations

- **Alembic is the sole schema manager** — no `create_all()` at startup.
- `001_initial.py` = base schema. `002_add_categories_and_confidence.py` = categories table + `categorize_confidence` column + 16 default categories seeded.
- Docker Compose runs `alembic upgrade head` explicitly before starting uvicorn.
- The backend lifespan handler also attempts auto-migration on startup, but silently skips errors (belt-and-suspenders).

## Lint / Testing Notes

- **Ruff** is the linter. B008 is ignored globally (FastAPI `Depends()` in argument defaults). T20 bans `print()` in app code but is allowed in tests.
- **pytest-asyncio** in auto mode — all async test functions auto-detected. Fixtures `db` and `client` are shared via `conftest.py`.
- Tests use in-memory SQLite and mock `SimpleFINClient` via `unittest.mock.patch`. Fixtures in `tests/fixtures/` provide SimpleFIN response data (initial + incremental).
- The `ENCRYPTION_KEY` env var is set in `conftest.py` before app module imports.
- Tests that need multiple syncs patch `MIN_SYNC_INTERVAL` to 0 to bypass rate limiting.
- LLM tests mock `GeminiClient` via `app.dependency_overrides[_get_client]` (FastAPI DI override).

## Configuration

Required env vars (see `.env.example`):
- `ENCRYPTION_KEY` — Fernet key (generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- `DATABASE_URL` — Default: `sqlite+aiosqlite:///./data/finance.db`
- `BACKEND_PORT` — Default: `8000`. Used by Docker Compose for port mapping.
- `FRONTEND_PORT` — Default: `5173`. Used by Docker Compose for port mapping.

SimpleFIN needs no env vars — the setup token is provided via the UI.

Optional env var for LLM features:
- `GEMINI_API_KEY` — Gemini API key (get from https://aistudio.google.com/apikey)

LLM application defaults (constants in `app/core/config.py`, not env-overridable):
`GEMINI_CATEGORIZE_MODEL`, `GEMINI_TEMPERATURE`, `GEMINI_MAX_TOKENS`, `CATEGORIZE_BATCH_SIZE`, `CATEGORIZE_LIMIT`, `CATEGORIZE_CONFIDENCE_THRESHOLD`.
