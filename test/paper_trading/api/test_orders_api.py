from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Self

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import paper_trading.services.order_service as order_service_module
from common.const import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN
from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_security_name_provider, get_session
from paper_trading.domain.enums import ETFEligibilityStatus, Market, OrderSide, OrderStatus
from paper_trading.schemas.orders import TradeListResponse
from paper_trading.storage.market_data import StorageMarketDataProvider
from paper_trading.storage.models import PaperCashLedger, PaperMatchingRun, PaperTrade
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from storage.model.etf_basic import ETFBasic
from test.paper_trading.fakes import FakeHistoryStorage, FakeTradeCalendar, _FakeSecurityNameProvider


class _TestDate(date):
    @classmethod
    def today(cls) -> Self:
        return cls(2026, 6, 16)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(order_service_module, "date", _TestDate)


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
    PaperTradingRepository(session).upsert_daily_bar_diagnostic(
        date(2026, 6, 16), Market.A_SHARE, "000001", "bfq", "missing_market_data", [], resolved=False
    )

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


def test_trade_list_response_exposes_pagination_envelope():
    response = TradeListResponse(
        items=[],
        page=1,
        page_size=50,
        total_count=0,
        total_pages=0,
    )

    assert response.items == []
    assert response.page == 1
    assert response.page_size == 50
    assert response.total_count == 0
    assert response.total_pages == 0


def test_create_order_queues_without_matching(monkeypatch, sqlite_session):
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
    PaperTradingRepository(session).upsert_daily_bar_diagnostic(
        date(2026, 6, 16), Market.A_SHARE, "000001", "bfq", "missing_market_data", [], resolved=False
    )

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
    assert payload["filled_quantity"] == 0
    trades_response = client.get(f"/paper/accounts/{account_id}/trades", headers=headers)
    trades = trades_response.json()
    assert trades == {"items": [], "page": 1, "page_size": 50, "total_count": 0, "total_pages": 0}


def test_create_order_idempotency_replays_original_order(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        FakeHistoryStorage({}), FakeTradeCalendar([date(2026, 7, 28)])
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_id = client.post(
        "/paper/accounts", json={"name": "demo", "initial_cash": "100000.00"}, headers=headers
    ).json()["id"]
    PaperTradingRepository(session).upsert_daily_bar_diagnostic(
        date(2026, 7, 28), Market.A_SHARE, "000001", "bfq", "missing_market_data", [], resolved=False
    )
    payload = {
        "symbol": "000001",
        "side": "buy",
        "quantity": 100,
        "limit_price": "10.00",
        "trade_date": "2026-07-28",
        "idempotency_key": "order-20260728-1",
    }

    first = client.post(f"/paper/accounts/{account_id}/orders", json=payload, headers=headers)
    second = client.post(f"/paper/accounts/{account_id}/orders", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert session.query(PaperCashLedger).filter_by(account_id=account_id, event_type="freeze").count() == 1
    assert session.query(PaperTrade).filter_by(account_id=account_id).count() == 0
    assert session.query(PaperMatchingRun).filter_by(account_id=account_id).count() == 0


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
    assert orders.json()["items"][0]["stock_name"] == "Tencent Holdings"
    assert trades.json()["items"][0]["stock_name"] == "Tencent Holdings"


def test_list_orders_returns_filtered_pagination_envelope(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_id = client.post(
        "/paper/accounts", json={"name": "paged", "initial_cash": "100000.00"}, headers=headers
    ).json()["id"]
    repo = PaperTradingRepository(session)
    repo.create_order(account_id, "000001", OrderSide.BUY, 100, Decimal("10"), date(2026, 8, 1), OrderStatus.ACCEPTED)
    second = repo.create_order(
        account_id, "000002", OrderSide.BUY, 100, Decimal("20"), date(2026, 8, 2), OrderStatus.ACCEPTED
    )
    latest = repo.create_order(
        account_id, "000003", OrderSide.BUY, 100, Decimal("30"), date(2026, 8, 2), OrderStatus.ACCEPTED
    )
    repo.create_order(account_id, "000004", OrderSide.BUY, 100, Decimal("40"), date(2026, 8, 3), OrderStatus.ACCEPTED)
    session.commit()

    response = client.get(
        f"/paper/accounts/{account_id}/orders?start_date=2026-08-01&end_date=2026-08-02&page=1&page_size=2",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [latest.id, second.id]
    assert payload["page"] == 1
    assert payload["page_size"] == 2
    assert payload["total_count"] == 3
    assert payload["total_pages"] == 2


def test_list_orders_validates_and_normalizes_pagination(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_id = client.post(
        "/paper/accounts", json={"name": "paged", "initial_cash": "100000.00"}, headers=headers
    ).json()["id"]
    repo = PaperTradingRepository(session)
    only_order = repo.create_order(
        account_id, "000001", OrderSide.BUY, 100, Decimal("10"), date(2026, 8, 1), OrderStatus.ACCEPTED
    )
    session.commit()

    invalid_page = client.get(f"/paper/accounts/{account_id}/orders?page=0", headers=headers)
    invalid_size = client.get(f"/paper/accounts/{account_id}/orders?page_size=101", headers=headers)
    invalid_range = client.get(
        f"/paper/accounts/{account_id}/orders?start_date=2026-08-02&end_date=2026-08-01", headers=headers
    )
    normalized = client.get(f"/paper/accounts/{account_id}/orders?page=99", headers=headers)
    empty = client.get(
        f"/paper/accounts/{account_id}/orders?start_date=2026-08-02&end_date=2026-08-02", headers=headers
    )

    assert invalid_page.status_code == 422
    assert invalid_size.status_code == 422
    assert invalid_range.status_code == 422
    assert normalized.json()["page"] == 1
    assert [item["id"] for item in normalized.json()["items"]] == [only_order.id]
    assert empty.json() == {"items": [], "page": 1, "page_size": 50, "total_count": 0, "total_pages": 0}


def test_list_trades_returns_filtered_pagination_envelope(monkeypatch, sqlite_session):
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
        "/paper/accounts", json={"name": "trades", "initial_cash": "100000.00"}, headers=headers
    ).json()["id"]
    repo = PaperTradingRepository(session)
    orders = [
        repo.create_order(account_id, symbol, OrderSide.BUY, 100, Decimal(price), trade_date, OrderStatus.FILLED)
        for symbol, price, trade_date in (
            ("000001", "10", date(2026, 8, 1)),
            ("00700", "20", date(2026, 8, 2)),
            ("000003", "30", date(2026, 8, 2)),
            ("000004", "40", date(2026, 8, 3)),
        )
    ]
    for order in orders:
        repo.create_trade(
            order_id=order.id,
            account_id=account_id,
            symbol=order.symbol,
            side=OrderSide.BUY,
            quantity=100,
            price=order.limit_price,
            amount=order.limit_price * 100,
            fees=Decimal("0"),
            trade_date=order.trade_date,
            market="hk_connect" if order.symbol == "00700" else "a_share",
        )
    session.commit()

    response = client.get(
        f"/paper/accounts/{account_id}/trades?start_date=2026-08-01&end_date=2026-08-02&page=1&page_size=2",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["symbol"] for item in payload["items"]] == ["000003", "00700"]
    assert payload["page"] == 1
    assert payload["page_size"] == 2
    assert payload["total_count"] == 3
    assert payload["total_pages"] == 2
    assert payload["items"][1]["stock_name"] == "Tencent Holdings"


def test_list_trades_validates_and_normalizes_pagination(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_id = client.post(
        "/paper/accounts", json={"name": "trades", "initial_cash": "100000.00"}, headers=headers
    ).json()["id"]
    repo = PaperTradingRepository(session)
    order = repo.create_order(
        account_id, "000001", OrderSide.BUY, 100, Decimal("10"), date(2026, 8, 1), OrderStatus.FILLED
    )
    repo.create_trade(
        order_id=order.id,
        account_id=account_id,
        symbol="000001",
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("10"),
        amount=Decimal("1000"),
        fees=Decimal("0"),
        trade_date=date(2026, 8, 1),
    )
    session.commit()

    invalid_page = client.get(f"/paper/accounts/{account_id}/trades?page=0", headers=headers)
    invalid_size = client.get(f"/paper/accounts/{account_id}/trades?page_size=101", headers=headers)
    invalid_range = client.get(
        f"/paper/accounts/{account_id}/trades?start_date=2026-08-02&end_date=2026-08-01", headers=headers
    )
    normalized = client.get(f"/paper/accounts/{account_id}/trades?page=99", headers=headers)
    empty = client.get(
        f"/paper/accounts/{account_id}/trades?start_date=2026-08-02&end_date=2026-08-02", headers=headers
    )

    assert invalid_page.status_code == 422
    assert invalid_size.status_code == 422
    assert invalid_range.status_code == 422
    assert normalized.json()["page"] == 1
    assert [item["id"] for item in normalized.json()["items"]] == [1]
    assert empty.json() == {"items": [], "page": 1, "page_size": 50, "total_count": 0, "total_pages": 0}


def test_create_etf_order_resolves_etf_names_and_rejects_unreviewed_etf(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    ETFBasic.__table__.create(session.get_bind(), checkfirst=True)
    repo = PaperTradingRepository(session)
    session.add_all(
        [
            ETFBasic(基金代码="510300", 中文简称="CSI 300 ETF", 交易所="SH", 存续状态="L"),
            ETFBasic(基金代码="159915", 中文简称="Unreviewed ETF", 交易所="SZ", 存续状态="L"),
        ]
    )
    repo.upsert_etf_eligibility(
        "510300",
        "CSI 300 ETF",
        "SH",
        "L",
        datetime(2026, 8, 12, tzinfo=timezone.utc),
        status=ETFEligibilityStatus.SUPPORTED,
    )
    session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_market_data_provider] = lambda: StorageMarketDataProvider(
        FakeHistoryStorage({}), FakeTradeCalendar([date(2026, 6, 16)])
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}
    account_id = client.post(
        "/paper/accounts", json={"name": "etf", "initial_cash": "100000.00"}, headers=headers
    ).json()["id"]

    accepted = client.post(
        f"/paper/accounts/{account_id}/orders",
        json={
            "symbol": "510300",
            "market": "etf",
            "side": "buy",
            "quantity": 100,
            "limit_price": "3.00",
            "trade_date": "2026-06-16",
        },
        headers=headers,
    )

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["market"] == "etf"
    order_id = accepted.json()["id"]
    repo.create_trade(
        order_id=order_id,
        account_id=account_id,
        symbol="510300",
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("3.00"),
        amount=Decimal("300.00"),
        fees=Decimal("0"),
        trade_date=date(2026, 6, 16),
        market=Market.ETF,
    )
    session.commit()

    orders = client.get(f"/paper/accounts/{account_id}/orders", headers=headers)
    trades = client.get(f"/paper/accounts/{account_id}/trades", headers=headers)
    assert orders.json()["items"][0]["stock_name"] == "CSI 300 ETF"
    assert trades.json()["items"][0]["stock_name"] == "CSI 300 ETF"

    rejected = client.post(
        f"/paper/accounts/{account_id}/orders",
        json={
            "symbol": "159915",
            "market": "etf",
            "side": "buy",
            "quantity": 100,
            "limit_price": "3.00",
            "trade_date": "2026-06-16",
        },
        headers=headers,
    )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_code"] == "ETF_ELIGIBILITY_UNREVIEWED"


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

    # Queued orders do not have trades until the matching workflow runs.
    trades_response = client.get(f"/paper/accounts/{account_id}/trades", headers=headers)
    trades = trades_response.json()
    assert trades == {"items": [], "page": 1, "page_size": 50, "total_count": 0, "total_pages": 0}

    # PATCH updates the queued order comment.
    order_id = payload["id"]
    patch_response = client.patch(
        f"/paper/orders/{order_id}/comment",
        json={"comment": "回踩确认后买入"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["comment"] == "回踩确认后买入"

    # PATCH with empty string clears the order comment.
    patch_response = client.patch(
        f"/paper/orders/{order_id}/comment",
        json={"comment": ""},
        headers=headers,
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["comment"] is None


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
