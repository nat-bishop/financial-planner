# Finance Planner

Personal finance app that syncs your bank accounts via [SimpleFIN Bridge](https://bridge.simplefin.org). Features smart transaction categorization that learns from your corrections.

## Quick Start

```bash
# Create .env file
cp .env.example .env

# Generate and add encryption key to .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Start with Docker (recommended)
make start          # Build & start backend + frontend
make logs           # Tail service logs
make stop           # Stop all services
```

Visit `http://localhost:5173` for the app, or `http://localhost:8000/docs` for API docs.

## SimpleFIN Setup

1. Go to [bridge.simplefin.org](https://bridge.simplefin.org) and create a setup token
2. Paste the token in the app UI
3. The app claims the token, stores encrypted credentials, and syncs your accounts

Setup tokens are one-time use. If you need to reconnect, get a new token.

## Local Development (no Docker)

```bash
# Install dependencies
uv sync
cd frontend && npm install

# Start both servers
make dev
```

## Commands

```bash
# Docker workflow (primary)
make start           # Build & start containers
make stop            # Stop all services
make logs            # Tail service logs
make restart         # Stop + start

# Local workflow
make dev             # Migrate + start backend & frontend locally
make migrate         # Apply migrations

# Quality
make test            # Run tests
make lint            # Lint with ruff
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Status, last sync time, account count |
| `/sync/credentials` | POST | Claim SimpleFIN setup token |
| `/sync/credentials` | DELETE | Remove stored credentials |
| `/sync/` | POST | Trigger sync (429 if rate limited, 409 if running) |
| `/accounts/` | GET | List accounts (with pagination) |
| `/accounts/{id}` | GET | Get single account |
| `/transactions/` | GET | List transactions (with filters + search) |
| `/transactions/{id}` | GET | Get single transaction |
| `/transactions/{id}` | PATCH | Update category/tags/notes (also trains category memory) |
| `/analytics/spending-by-category` | GET | Spending totals by category |
| `/llm/status` | GET | LLM configuration status |
| `/llm/categorize` | POST | Auto-categorize transactions (memory matching + LLM fallback) |
| `/providers/` | GET | List providers with connection status |
| `/providers/{name}/credentials` | POST | Store provider credentials |
| `/providers/{name}/credentials` | DELETE | Remove provider credentials |

## Configuration

Environment variables (see `.env.example`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENCRYPTION_KEY` | Yes | - | Fernet key for credential encryption |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./data/finance.db` | Database connection string |
| `BACKEND_PORT` | No | `8000` | Backend port (Docker) |
| `FRONTEND_PORT` | No | `5173` | Frontend port (Docker) |
| `GEMINI_API_KEY` | No | - | Gemini API key for LLM categorization |

SimpleFIN needs no env vars — the setup token is provided via the UI.

## Smart Categorization

The app learns from your corrections to auto-categorize future transactions:

1. **Correct a transaction** — PATCH a transaction's category, and the app remembers that description pattern
2. **Auto-categorize** — When you click "Auto-Categorize", matching descriptions are instantly categorized from memory; only unknown descriptions go to the LLM
3. **Sync auto-apply** — New transactions matching known patterns are categorized automatically on sync, no LLM needed
4. **LLM gets smarter** — Your corrections are injected as few-shot examples in the LLM prompt, improving accuracy for similar transactions

Memory entries are scoped per account, so "PAYMENT" on your credit card can map to a different category than "PAYMENT" on your checking account.

## Tech Stack

- **FastAPI** - Web framework
- **SQLAlchemy 2.0** - Async ORM with aiosqlite
- **Alembic** - Database migrations
- **Pydantic 2.0** - Data validation
- **SimpleFIN Bridge** - Banking data aggregation
- **Fernet** - Credential encryption
- **Vue 3 + Vite** - Frontend framework
- **Tailwind CSS v4** - Styling
- **Pinia** - State management
