import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine
from app.routes import router

log = logging.getLogger(__name__)


def _run_migrations() -> None:
    """Run Alembic migrations to head on startup."""
    from alembic import command  # noqa: I001
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    Path("data").mkdir(parents=True, exist_ok=True)
    try:
        # Run in thread — alembic env.py calls asyncio.run() which needs its own loop
        await asyncio.to_thread(_run_migrations)
    except Exception:
        log.warning("Auto-migration skipped (alembic.ini not found or error)")
    yield
    await engine.dispose()


app = FastAPI(
    title="Finance Planner",
    description="Personal finance app with multi-provider sync",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {
        "name": "Finance Planner",
        "version": "0.1.0",
        "docs": "/docs",
    }
