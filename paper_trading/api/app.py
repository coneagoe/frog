from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from paper_trading.api.routers import accounts, analytics, matching, orders, snapshots
from storage.storage_db import get_storage


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Account-only API routes do not otherwise initialize StorageDb.
    # Bootstrap it here so legacy paper-trading schemas are upgraded at startup.
    get_storage()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Frog Paper Trading", lifespan=lifespan)

    app.include_router(accounts.router)
    app.include_router(orders.router)
    app.include_router(matching.router)
    app.include_router(snapshots.router)
    app.include_router(analytics.router)
    return app
