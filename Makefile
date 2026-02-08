.PHONY: start stop logs restart dev migrate test lint

# Docker workflow (primary)
start:
	docker compose down --remove-orphans
	docker compose up -d --build

stop:
	docker compose down --remove-orphans

logs:
	docker compose logs -f

restart: stop start

# Local workflow (no Docker)
migrate:
	uv run alembic upgrade head

dev: migrate
	@trap 'kill 0' EXIT; \
	uv run uvicorn app.main:app --reload & \
	cd frontend && npm run dev

# Quality
test:
	pytest

lint:
	ruff check app tests
