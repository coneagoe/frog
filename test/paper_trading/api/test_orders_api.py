from datetime import date
from decimal import Decimal

import pandas as pd
from fastapi.testclient import TestClient

from common.const import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN
from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_security_name_provider, get_session
from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.storage.market_data import StorageMarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from test.paper_trading.fakes import FakeHistoryStorage, FakeTradeCalendar


class _FakeSecurityNameProvider:
    def __init__(self, names):
        self.names = names

    def resolve_names(self, securities):
        return {security: self.names[security] for security in securities if security in self.names}


def test_create_order_returns_accepted_order(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    storage = FakeHistoryStorage({})
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 6, 16)]),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_response = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    )
    account_id = account_response.json()["id"]

    response = client.post(
        f"/paper/accounts/{account_id}/orders",
        json={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": "10.00",
            "trade_date": "2026-06-16",
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["symbol"] == "000001"
    assert payload["quantity"] == 100
    assert payload["limit_price"] == "10.0000"


def test_create_order_auto_matches_when_limit_is_touched(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    storage = FakeHistoryStorage(
        {
            "000001": pd.DataFrame(
                [
                    {
                        COL_DATE: "2026-06-16",
                        COL_OPEN: "9.90",
                        COL_HIGH: "10.10",
                        COL_LOW: "9.80",
                        COL_CLOSE: "10.00",
                    }
                ]
            )
        }
    )
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 6, 16)]),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_response = client.post(
        "/paper/accounts", json={"name": "demo", "initial_cash": "100000.00"}, headers=headers
    )
    account_id = account_response.json()["id"]

    response = client.post(
        f"/paper/accounts/{account_id}/orders",
        json={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": "10.00",
            "trade_date": "2026-06-16",
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "filled"
    assert payload["filled_quantity"] == 100
    trades_response = client.get(f"/paper/accounts/{account_id}/trades", headers=headers)
    trades = trades_response.json()
    assert len(trades) == 1
    assert trades[0]["order_id"] == payload["id"]


def test_list_orders_and_trades_include_stock_name(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_security_name_provider] = lambda: _FakeSecurityNameProvider(
        {("hk_connect", "00700"): "Tencent Holdings"}
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_id = client.post(
        "/paper/accounts", json={"name": "demo", "initial_cash": "100000.00"}, headers=headers
    ).json()["id"]
    repo = PaperTradingRepository(session)
    order = repo.create_order(
        account_id=account_id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400"),
        trade_date=date(2026, 6, 16),
        status=OrderStatus.FILLED,
        market="hk_connect",
    )
    repo.create_trade(
        order_id=order.id,
        account_id=account_id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("400"),
        amount=Decimal("40000"),
        fees=Decimal("0"),
        trade_date=date(2026, 6, 16),
        market="hk_connect",
    )
    session.commit()
    orders = client.get(f"/paper/accounts/{account_id}/orders", headers=headers)
    trades = client.get(f"/paper/accounts/{account_id}/trades", headers=headers)
    assert orders.status_code == 200
    assert trades.status_code == 200
    assert orders.json()[0]["stock_name"] == "Tencent Holdings"
    assert trades.json()[0]["stock_name"] == "Tencent Holdings"


def test_create_order_returns_validity_summary(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    storage = FakeHistoryStorage({})
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 6, 16)]),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_response = client.post(
        "/paper/accounts", json={"name": "demo", "initial_cash": "100000.00"}, headers=headers
    )
    account_id = account_response.json()["id"]

    response = client.post(
        f"/paper/accounts/{account_id}/orders",
        json={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": "10.00",
            "trade_date": "2026-06-16",
        },
        headers=headers,
    )

    payload = response.json()
    assert "validity_status" in payload
    assert "validity_reason" in payload
    assert "validity_checked_at" in payload


def test_create_order_missing_account_returns_404(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    storage = FakeHistoryStorage({})
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 6, 16)]),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}

    response = client.post(
        "/paper/accounts/999/orders",
        json={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": "10.00",
            "trade_date": "2026-06-16",
        },
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "paper account not found: 999"


def test_get_order_validity_checks_returns_evidence(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    storage = FakeHistoryStorage({})
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 6, 16)]),
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
            "trade_date": "2026-06-16",
        },
        headers=headers,
    )
    order_id = order_response.json()["id"]

    response = client.get(f"/paper/accounts/{account_id}/orders/{order_id}/validity-checks", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["order_id"] == order_id
    assert payload[0]["data_granularity"] == "daily"


def test_order_comment_is_created_copied_to_trade_and_updated(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    storage = FakeHistoryStorage(
        {
            "000001": pd.DataFrame(
                [
                    {
                        COL_DATE: "2026-07-18",
                        COL_OPEN: "9.90",
                        COL_HIGH: "10.10",
                        COL_LOW: "9.80",
                        COL_CLOSE: "10.00",
                    }
                ]
            )
        }
    )
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 7, 18)]),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_response = client.post(
        "/paper/accounts", json={"name": "demo", "initial_cash": "100000.00"}, headers=headers
    )
    account_id = account_response.json()["id"]

    # Create order with comment
    response = client.post(
        f"/paper/accounts/{account_id}/orders",
        json={
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "limit_price": "10.00",
            "trade_date": "2026-07-18",
            "comment": "突破买入",
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["comment"] == "突破买入"

    # Trade list has the same comment
    trades_response = client.get(f"/paper/accounts/{account_id}/trades", headers=headers)
    trades = trades_response.json()
    assert len(trades) == 1
    assert trades[0]["comment"] == "突破买入"

    # PATCH with new comment updates both order and trade
    order_id = payload["id"]
    patch_response = client.patch(
        f"/paper/orders/{order_id}/comment",
        json={"comment": "回踩确认后买入"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["comment"] == "回踩确认后买入"

    trades_response = client.get(f"/paper/accounts/{account_id}/trades", headers=headers)
    assert trades_response.json()[0]["comment"] == "回踩确认后买入"

    # PATCH with empty string returns comment is None and trade comment is None
    patch_response = client.patch(
        f"/paper/orders/{order_id}/comment",
        json={"comment": ""},
        headers=headers,
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["comment"] is None

    trades_response = client.get(f"/paper/accounts/{account_id}/trades", headers=headers)
    assert trades_response.json()[0]["comment"] is None


def test_update_order_comment_missing_order_returns_404(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    storage = FakeHistoryStorage({})
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 7, 18)]),
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}

    response = client.patch(
        "/paper/orders/99999/comment",
        json={"comment": "new reason"},
        headers=headers,
    )
    assert response.status_code == 404
    assert "paper order not found: 99999" in response.json()["detail"]
