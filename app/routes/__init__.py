from fastapi import APIRouter

from app.routes import accounts, analytics, health, sync, transactions

router = APIRouter()

router.include_router(health.router, tags=["health"])
router.include_router(sync.router, prefix="/sync", tags=["sync"])
router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
