# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Finance Planner is a personal finance application that syncs financial data from multiple providers (SimpleFIN Bridge, Nelnet). It provides account management, transaction tracking, and spending analytics with encrypted credential storage. Syncs run as background tasks with 2FA relay for browser-based providers.

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
1. User connects a provider via `POST /providers/{name}/credentials` (SimpleFIN setup token, Nelnet username/password)
2. `POST /sync/` or `POST /sync/{provider}` returns **202 immediately** with SyncLog IDs. Sync runs as a background `asyncio.Task`.
3. Frontend polls `GET /sync/status` for per-provider progress (running, success, failed, awaiting_2fa).
4. If a browser provider (Nelnet) hits a 2FA challenge, the SyncLog transitions to `awaiting_2fa`. Frontend shows `TwoFAModal`, user submits code via `POST /sync/{id}/2fa`, code is relayed to the waiting browser task.
5. Upserts preserve user-managed fields (category, tags, notes) while overwriting provider fields (amount, description, is_pending).
6. Per-provider rate limits: SimpleFIN 24/day, Nelnet 4/day. Returns 429 if exceeded. Returns 409 if sync already running for that provider.

### Layered Architecture

```
app/
├── main.py                    # App assembly + lifespan (stale sync cleanup)
├── models.py                  # SQLAlchemy models (Credential, Account, Transaction, SyncLog, Category, CategoryMemory)
├── schemas.py                 # Pydantic schemas
├── core/                      # Shared infrastructure
│   ├── config.py              # Pydantic settings from .env
│   ├── database.py            # Session factory (get_db dependency)
│   └── encryption.py          # Fernet encrypt/decrypt
├── clients/                   # External API clients (pure HTTP, no DB)
│   ├── simplefin.py           # SimpleFIN Bridge client (httpx)
│   └── gemini.py              # Gemini structured output client (google-genai)
├── providers/                 # Provider abstraction layer
│   ├── base.py                # FinanceProvider ABC + error types + TwoFAHandler
│   ├── models.py              # ProviderAccount, ProviderTransaction, SyncResult
│   ├── simplefin.py           # SimpleFIN adapter (wraps clients/simplefin.py)
│   ├── browser.py             # BrowserProvider base (Playwright + stealth)
│   ├── nelnet.py              # Nelnet scraper (extends BrowserProvider)
│   └── __init__.py            # Provider registry (get_provider, list_providers)
├── services/                  # Business logic (orchestration, DB writes)
│   ├── sync.py                # Background sync tasks, 2FA relay, rate limits
│   ├── two_fa.py              # TwoFASession in-memory coordination (asyncio.Event)
│   └── categorize.py          # Batch transaction categorization
├── routes/                    # Thin HTTP handlers
│   ├── accounts.py, analytics.py, health.py, transactions.py
│   ├── sync.py                # Sync triggers (202), status polling, 2FA endpoints
│   ├── providers.py           # Provider list + credential CRUD
│   ├── categories.py          # Category CRUD
│   └── llm.py                 # LLM status + categorize endpoints
```

**Layer rules:** `core/` = infrastructure, `clients/` = pure HTTP (no DB), `providers/` = data fetching (no DB, returns data only), `services/` = business logic + DB writes, `routes/` = thin handlers.

### Key Modules
- `app/services/sync.py` — Background sync orchestration. `start_sync()` creates a SyncLog, spawns `asyncio.create_task(_background_sync(...))`, returns immediately. Per-provider `asyncio.Lock` prevents concurrent syncs. Background task gets its own DB session via `async_session_maker()`. Browser providers get a 600s timeout (vs 30s for API providers).
- `app/services/two_fa.py` — In-memory 2FA coordination. `TwoFASession` uses `asyncio.Event` to block the background sync task until a code arrives. Module-level `_active_sessions` dict keyed by `sync_log_id`. 10-minute timeout, 3 retry attempts. Sessions are cleaned up in the `finally` block of `_background_sync`.
- `app/providers/base.py` — `FinanceProvider` ABC with `validate_credentials()` and `sync()`. `TwoFAHandler = Callable[[TwoFAChallenge], Awaitable[str]]` — async callback passed to browser providers for 2FA relay.
- `app/routes/sync.py` — `POST /sync/` and `POST /sync/{provider}` return 202. `GET /sync/status` returns per-provider status. `POST /sync/{id}/2fa` relays codes to the background task. `GET /sync/{id}/2fa` returns challenge details.
- `app/routes/providers.py` — `GET /providers/`, `POST/PUT/DELETE /providers/{name}/credentials`.
- `app/clients/simplefin.py` — Async SimpleFIN Bridge client using `httpx.AsyncClient`. Amount parsing via `decimal.Decimal`.
- `app/clients/gemini.py` — Gemini client with `generate_structured()` (Pydantic response_schema + retry). Singleton via `get_gemini_client()`.
- `app/services/categorize.py` — Batch categorization with category memory: deterministic matching (`apply_memory_rules()`) before LLM, caches LLM results (`cache_llm_results()`), few-shot prompt context from memory entries.
- `app/core/database.py` — Session factory with auto-commit on success, auto-rollback on exception (via `get_db` dependency). `async_session_maker` used directly by background tasks (no request-scoped `get_db`).
- `app/core/config.py` — Pydantic settings from `.env`. See `.env.example` for required vars.

### Critical Conventions
- **Amounts in cents** as integers. **Sign convention:** negative = expense, positive = income. **Matches SimpleFIN** (no sign inversion needed). Conversion in `_sfin_amount_to_cents()`.
- **Dates** as Unix timestamps (integers). SimpleFIN uses Unix timestamps natively. Pending transactions have `posted=0`, substituted with current timestamp.
- **Upsert field split:** On conflict, `posted_at`, `amount`, `description`, `is_pending`, `raw_data` are overwritten. `category`, `subcategory`, `tags`, `notes` are preserved. This is what makes user edits survive re-syncs.
- **No transaction removal:** SimpleFIN doesn't report removed transactions.
- **Background sync:** All syncs run as `asyncio.Task`s. The HTTP handler creates the SyncLog, spawns the task, and returns 202. The background task uses its own DB session (`async_session_maker()`), not the request's session. On server restart, the lifespan handler marks stale `running`/`awaiting_2fa` SyncLogs as failed.
- **2FA relay:** Browser providers call `two_fa_handler(challenge)` which blocks on `asyncio.Event.wait()`. The frontend polls `/sync/status`, detects `awaiting_2fa`, shows `TwoFAModal.vue`, and submits the code via `POST /sync/{id}/2fa`. The code is passed through to the waiting task. 10-minute timeout, 3 attempts max.
- **SyncLog statuses:** `running` → `success` or `failed`. Browser providers can also go `running` → `awaiting_2fa` → `running` → `success`. The `two_fa_status` column tracks sub-states: `awaiting_code`, `code_submitted`, `timed_out`.
- **Setup tokens are one-time use.** A 403 on claim means the token was already used — get a new one.
- **Category states:** `category = "Uncategorized"` = not yet categorized. `category = "Unable to Categorize"` + `categorize_confidence IS NOT NULL` = LLM tried, below threshold. `category = "Food & Dining"` + `categorize_confidence = 0.92` = LLM categorized. `category = "Food & Dining"` + `categorize_confidence IS NULL` = user manually set or memory-matched.
- **Confidence threshold** is evaluated only at categorize time. Changing `CATEGORIZE_CONFIDENCE_THRESHOLD` does NOT retroactively change existing categorizations.
- **Category memory:** `category_memory` table remembers `(normalized_pattern, account_id) → (category, subcategory)`. User corrections upsert (always win). LLM results insert-if-absent (never overwrite). `normalize_description()` strips trailing dates, ref numbers, and normalizes whitespace. On sync, memory rules auto-apply to new uncategorized transactions (no LLM). On categorize, memory matching runs before LLM, and LLM results are cached after.

### Frontend
- Vite proxies `/api/*` → backend (strips `/api` prefix). Default target `http://localhost:8000` for local dev; Docker sets `VITE_API_URL=http://backend:<port>` via compose environment.
- The `useApi.ts` composable prefixes all fetch calls with `/api`.
- Tailwind CSS **v4** — uses `@import "tailwindcss"` and `@theme {}` blocks in `style.css`, not a v3 tailwind.config.
- Pinia stores in `src/stores/` (accounts, transactions, sync, categories, llm).
- **Sync polling:** `useSyncStore` polls `GET /sync/status` while any provider is running or awaiting 2FA. Per-provider status displayed in the UI.
- **2FA modal:** `TwoFAModal.vue` appears when polling detects `awaiting_2fa`. Submits code via `syncStore.submit2FACode()` → `POST /sync/{id}/2fa`. Auto-focuses input, supports Enter to submit.
- **Provider connect flow:** `SimpleFINConnect.vue` and `NelnetConnect.vue` are hardcoded components. Credential management via `/providers/{name}/credentials`.

### Docker & Infrastructure
- **Primary workflow:** `make start` / `make stop`. Runs via Docker Compose.
- **Playwright in Docker:** Dockerfile installs Chromium binary + OS deps (`playwright install-deps chromium` + `playwright install chromium`). All providers (including browser-based Nelnet) work in Docker.
- **Port configuration:** `BACKEND_PORT` and `FRONTEND_PORT` in `.env`, referenced in `docker-compose.yml` via `${VAR:-default}` interpolation.
- **Health check:** Backend exposes `GET /health` (queries DB). Docker Compose uses it with `condition: service_healthy` so frontend waits for backend readiness.
- **Hot reload:** Source volumes mounted (`./app`, `./frontend/src`) for live reload in containers.
- **Data persistence:** `db-data` Docker volume stores SQLite database across restarts.
- **Local fallback:** `make dev` runs both servers directly (no Docker). Uses `trap 'kill 0' EXIT` for cleanup.

## Migrations

- **Alembic is the sole schema manager** — no `create_all()` at startup.
- `001_initial.py` = base schema. `002_add_categories_and_confidence.py` = categories table + `categorize_confidence` column + 16 default categories seeded. `007_add_category_memory.py` = `category_memory` table for description pattern → category mapping. `008_add_2fa_fields.py` = `two_fa_status` and `two_fa_method` columns on `sync_log`.
- Docker Compose runs `alembic upgrade head` explicitly before starting uvicorn.
- The backend lifespan handler also attempts auto-migration on startup, but silently skips errors (belt-and-suspenders). After migrations, it marks stale `running`/`awaiting_2fa` SyncLogs as failed (orphaned from a previous process exit).

## Lint / Testing Notes

- **Ruff** is the linter. B008 is ignored globally (FastAPI `Depends()` in argument defaults). T20 bans `print()` in app code but is allowed in tests.
- **pytest-asyncio** in auto mode — all async test functions auto-detected. Fixtures `db` and `client` are shared via `conftest.py`.
- Tests use in-memory SQLite and mock `SimpleFINClient` via `unittest.mock.patch`. Fixtures in `tests/fixtures/` provide SimpleFIN response data (initial + incremental).
- The `ENCRYPTION_KEY` env var is set in `conftest.py` before app module imports.
- Tests that need multiple syncs patch `MIN_SYNC_INTERVAL` to 0 to bypass rate limiting.
- LLM tests mock `GeminiClient` via `app.dependency_overrides[_get_client]` (FastAPI DI override).
- 2FA tests (`tests/test_two_fa.py`) test the `TwoFASession` directly — event coordination, timeout, retry, max attempts. Uses `autouse` fixture to clear `_active_sessions` between tests.

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
