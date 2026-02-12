import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_maker, engine
from app.routes import router

# Ensure app-level loggers output to console
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("app").setLevel(logging.INFO)

log = logging.getLogger(__name__)


def _run_migrations() -> None:
    """Run Alembic migrations to head on startup."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_cfg, "head")


async def _mark_stale_syncs() -> None:
    """Mark running/awaiting_2fa SyncLogs as failed on startup.

    These are orphaned from a previous process that exited before completion.
    """
    from app.models import SyncLog

    try:
        async with async_session_maker() as db:
            stale = await db.scalars(
                select(SyncLog).where(SyncLog.status.in_(["running", "awaiting_2fa"]))
            )
            now = int(time.time())
            count = 0
            for entry in stale.all():
                entry.status = "failed"
                entry.error_message = "Stale: server restarted"
                entry.completed_at = now
                count += 1
            if count:
                await db.commit()
                log.info("Marked %d stale sync log(s) as failed", count)
    except Exception:
        log.warning("Could not clean up stale sync logs (DB may not exist yet)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path("data").mkdir(parents=True, exist_ok=True)
    try:
        # Run in thread — alembic env.py calls asyncio.run() which needs its own loop
        await asyncio.to_thread(_run_migrations)
    except Exception:
        log.warning("Auto-migration skipped (alembic.ini not found or error)")

    await _mark_stale_syncs()

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
