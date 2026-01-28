# Finance Planner

Personal finance app that syncs your bank accounts via SimpleFIN.

## Quick Start

```bash
# Install dependencies
uv sync

# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Create .env file
cp .env.example .env
# Add your ENCRYPTION_KEY to .env

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs.

## Setup SimpleFIN

1. Get a setup token from [SimpleFIN](https://beta-bridge.simplefin.org)
2. Claim it via API:
```bash
curl -X POST http://localhost:8000/sync/credentials \
  -H "Content-Type: application/json" \
  -d '{"setup_token": "YOUR_BASE64_TOKEN"}'
```
3. Trigger a sync:
```bash
curl -X POST http://localhost:8000/sync/
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Status, last sync time, account count |
| `/sync/credentials` | POST | Claim SimpleFIN setup token |
| `/sync/credentials` | DELETE | Remove stored credentials |
| `/sync/` | POST | Trigger sync (optional date range) |
| `/sync/history` | GET | Sync operation history |
| `/accounts` | GET | List all accounts |
| `/accounts/{id}` | GET | Get single account |
| `/transactions` | GET | List transactions (with filters) |
| `/transactions/{id}` | GET | Get single transaction |
| `/transactions/{id}` | PATCH | Update category/tags/notes |
| `/analytics/spending-by-category` | GET | Spending totals by category |

## Configuration

Environment variables (see `.env.example`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENCRYPTION_KEY` | Yes | - | Fernet key for credential encryption |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./data/finance.db` | Database connection string |
| `SIMPLEFIN_BASE_URL` | No | `https://beta-bridge.simplefin.org` | SimpleFIN API URL |

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
pytest

# Run specific test file
pytest tests/test_api.py -v

# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Revert last migration
alembic downgrade -1
```

## Tech Stack

- **FastAPI** - Web framework
- **SQLAlchemy 2.0** - Async ORM with aiosqlite
- **Alembic** - Database migrations
- **Pydantic 2.0** - Data validation
- **Fernet** - Credential encryption
- **httpx** - Async HTTP client
