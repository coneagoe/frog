from fastapi import FastAPI

from paper_trading.api.routers import accounts, matching, orders, snapshots


def create_app() -> FastAPI:
    app = FastAPI(title="Frog Paper Trading")
    app.include_router(accounts.router)
    app.include_router(orders.router)
    app.include_router(matching.router)
    app.include_router(snapshots.router)
    return app
