# Finance Planner

Personal finance app that syncs your bank accounts via Plaid.

## Quick Start

```bash
# Install dependencies
uv sync

# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Create .env file
cp .env.example .env
# Add your ENCRYPTION_KEY and Plaid credentials to .env

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs.

## Plaid Setup

### Sandbox (Testing)

1. Sign up at [Plaid Dashboard](https://dashboard.plaid.com) and get sandbox credentials
2. Add to `.env`:
   ```
   PLAID_CLIENT_ID=your_client_id
   PLAID_SECRET=your_sandbox_secret
   PLAID_ENVIRONMENT=sandbox
   ```
3. Create test credentials (bypasses Plaid Link):
   ```bash
   curl -X POST http://localhost:8000/sync/sandbox-token
   ```
4. Trigger a sync:
   ```bash
   curl -X POST http://localhost:8000/sync/
   ```

### Production

1. Get production credentials from Plaid Dashboard
2. Set `PLAID_ENVIRONMENT=production` in `.env`
3. Use `POST /sync/link-token` to get a Link token for the frontend
4. After user completes Plaid Link, exchange the public token:
   ```bash
   curl -X POST http://localhost:8000/sync/credentials \
     -H "Content-Type: application/json" \
     -d '{"public_token": "PUBLIC_TOKEN_FROM_LINK"}'
   ```
5. Trigger syncs with `POST /sync/`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Status, last sync time, account count |
| `/sync/sandbox-token` | POST | Create sandbox credentials (testing only) |
| `/sync/link-token` | POST | Create Plaid Link token for frontend |
| `/sync/credentials` | POST | Exchange Plaid public token for credentials |
| `/sync/credentials` | DELETE | Remove stored credentials |
| `/sync/` | POST | Trigger sync (returns 409 if already running) |
| `/sync/history` | GET | Sync operation history |
| `/accounts/` | GET | List accounts (with pagination) |
| `/accounts/{id}` | GET | Get single account |
| `/transactions/` | GET | List transactions (with filters + search) |
| `/transactions/{id}` | GET | Get single transaction |
| `/transactions/{id}` | PATCH | Update category/tags/notes |
| `/analytics/spending-by-category` | GET | Spending totals by category |

## Configuration

Environment variables (see `.env.example`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENCRYPTION_KEY` | Yes | - | Fernet key for credential encryption |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./data/finance.db` | Database connection string |
| `PLAID_CLIENT_ID` | Yes | - | Plaid API client ID |
| `PLAID_SECRET` | Yes | - | Plaid API secret |
| `PLAID_ENVIRONMENT` | No | `sandbox` | `sandbox` \| `development` \| `production` |

## Frontend

```bash
cd frontend
npm install
npm run dev    # Starts on http://localhost:5173
```

The Vite dev server proxies `/api/*` requests to the backend at `http://localhost:8000`.

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
pytest

# Run specific test file
pytest tests/test_api.py -v

# Lint
ruff check app tests

# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## Tech Stack

- **FastAPI** - Web framework
- **SQLAlchemy 2.0** - Async ORM with aiosqlite
- **Alembic** - Database migrations
- **Pydantic 2.0** - Data validation
- **Plaid SDK** - Banking data aggregation
- **Fernet** - Credential encryption
- **Vue 3** - Frontend framework
- **Tailwind CSS** - Styling
