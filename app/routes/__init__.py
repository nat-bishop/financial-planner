from fastapi import APIRouter

from app.routes import (
    accounts,
    analytics,
    categories,
    health,
    llm,
    providers,
    settings,
    sync,
    transactions,
)

router = APIRouter()

router.include_router(health.router, tags=["health"])
router.include_router(providers.router, prefix="/providers", tags=["providers"])
router.include_router(sync.router, prefix="/sync", tags=["sync"])
router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
router.include_router(
    transactions.router, prefix="/transactions", tags=["transactions"]
)
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
router.include_router(categories.router, prefix="/categories", tags=["categories"])
router.include_router(settings.router, prefix="/settings", tags=["settings"])
router.include_router(llm.router, prefix="/llm", tags=["llm"])
