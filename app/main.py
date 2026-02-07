from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.models import Base
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data directory exists
    Path("data").mkdir(parents=True, exist_ok=True)

    # Create tables if they don't exist (for development)
    # In production, use alembic migrations
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Cleanup
    await engine.dispose()


app = FastAPI(
    title="Finance Planner",
    description="Personal finance app with Plaid sync",
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
