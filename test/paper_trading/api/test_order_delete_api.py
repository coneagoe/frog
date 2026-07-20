from datetime import date

from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_session
from paper_trading.storage.market_data import StorageMarketDataProvider
from storage.model.base import Base
from test.paper_trading.fakes import FakeHistoryStorage, FakeTradeCalendar


def test_delete_order_returns_204(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    storage = FakeHistoryStorage({})
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 7, 19)]),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_response = client.post(
        "/paper/accounts", json={"name": "demo", "initial_cash": "100000.00"}, headers=headers
    )
    account_id = account_response.json()["id"]

    order_response = client.post(
        f"/paper/accounts/{account_id}/orders",
        json={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": "10.00",
            "trade_date": "2026-07-19",
        },
        headers=headers,
    )
    order_id = order_response.json()["id"]

    response = client.delete(f"/paper/orders/{order_id}", headers=headers)

    assert response.status_code == 204


def test_delete_missing_order_returns_404(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    storage = FakeHistoryStorage({})
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 7, 19)]),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}

    response = client.delete("/paper/orders/999999", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "paper order not found: 999999"
