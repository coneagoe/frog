from fastapi import FastAPI

from paper_trading.api.routers import accounts, analytics, matching, orders, snapshots


def create_app() -> FastAPI:
    app = FastAPI(title="Frog Paper Trading")
    app.include_router(accounts.router)
    app.include_router(orders.router)
    app.include_router(matching.router)
    app.include_router(snapshots.router)
    app.include_router(analytics.router)
    return app
