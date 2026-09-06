from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from paper_trading.api.routers import (
    accounts,
    analytics,
    auth,
    corporate_actions,
    etf_eligibility,
    matching,
    monitor_targets,
    orders,
    repairs,
    snapshot_recalculation,
    snapshots,
)
from paper_trading.auth import AuthSettings
from storage.storage_db import get_storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.auth_settings = AuthSettings.from_environment()
    # Account-only API routes do not otherwise initialize StorageDb.
    # Bootstrap it here so legacy paper-trading schemas are upgraded at startup.
    get_storage()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Frog Paper Trading", lifespan=lifespan)

    app.include_router(accounts.router)
    app.include_router(auth.router)
    app.include_router(orders.router)
    app.include_router(matching.router)
    app.include_router(monitor_targets.router)
    app.include_router(snapshots.router)
    app.include_router(snapshot_recalculation.router)
    app.include_router(analytics.router)
    app.include_router(corporate_actions.router)
    app.include_router(etf_eligibility.router)
    app.include_router(repairs.router)
    return app
