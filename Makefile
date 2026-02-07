.PHONY: dev migrate

migrate:
	uv run alembic upgrade head

dev: migrate
	@trap 'kill 0' EXIT; \
	uv run uvicorn app.main:app --reload & \
	cd frontend && npm run dev
