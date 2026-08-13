from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_session
from paper_trading.domain.enums import Market, OrderSide, OrderStatus
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def test_matching_api_records_snapshot_market_data_failure(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("api-failure", Decimal("100000.00"))
    repo.upsert_daily_bar_diagnostic(
        date(2026, 7, 27),
        Market.A_SHARE,
        "00700",
        "bfq",
        "missing_market_data",
        [],
        resolved=False,
    )
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 7, 27),
        status=OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1001.0000"),
    )

    class MarketData:
        def __init__(self):
            self.calls = 0

        def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
            return None

        def get_daily_bar(self, symbol, trade_date, market=None):
            self.calls += 1
            if self.calls == 1:
                return DailyBar(symbol, trade_date, Decimal("10"), Decimal("100"), Decimal("1"), Decimal("50"))
            raise KeyError("No daily bar for 00700 on 2026-07-27")

    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    app.dependency_overrides[get_market_data_provider] = lambda: MarketData()

    response = TestClient(app).post(
        "/paper/matching/runs",
        json={"trade_date": "2026-07-27", "account_id": account.id},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed_with_warnings"
    assert body["warning_count"] == 1
    gap = repo.get_valuation_gap(account.id, date(2026, 7, 27))
    assert gap is not None
    assert gap.resolved is False
    assert gap.missing_symbols == ["00700"]
    assert repo.list_snapshots(account.id) == []
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    assert len(repo.list_trades(account.id)) == 1


def test_matching_rebuild_api_replays_eligible_delayed_order(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("rebuild-api", Decimal("100000.00"))
    trade_date = date(2026, 7, 27)
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.A_SHARE, "000001", "bfq", "missing_exact_date", [], resolved=False
    )

    class MarketData:
        def get_daily_bar(self, symbol, requested_date, market=None):
            return DailyBar(symbol, requested_date, Decimal("10"), Decimal("100"), Decimal("1"), Decimal("50"))

        def get_latest_daily_close(self, symbol, requested_date, market=None):
            return Decimal("50")

        def next_trade_date(self, requested_date):
            return requested_date

    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    app.dependency_overrides[get_market_data_provider] = lambda: MarketData()

    response = TestClient(app).post("/paper/matching/runs/rebuilds", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {"rebuilt_account_ids": [account.id]}
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value


def test_matching_rebuild_api_replays_only_etf_raw_missing_date_order(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    trade_date = date(2026, 8, 10)
    etf_account = repo.create_account("etf-rebuild-api", Decimal("100000.00"))
    legacy_etf_account = repo.create_account("etf-qfq-diagnostic", Decimal("100000.00"))
    a_share_account = repo.create_account("a-share-qfq-diagnostic", Decimal("100000.00"))
    hk_account = repo.create_account("hk-qfq-diagnostic", Decimal("100000.00"))
    etf_order = repo.create_order(
        etf_account.id,
        "510300",
        OrderSide.BUY,
        100,
        Decimal("3.100"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("311.0000"),
        market=Market.ETF,
    )
    a_share_order = repo.create_order(
        a_share_account.id,
        "510300",
        OrderSide.BUY,
        100,
        Decimal("3.100"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("311.0000"),
        market=Market.A_SHARE,
    )
    legacy_etf_order = repo.create_order(
        legacy_etf_account.id,
        "510500",
        OrderSide.BUY,
        100,
        Decimal("3.100"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("311.0000"),
        market=Market.ETF,
    )
    hk_order = repo.create_order(
        hk_account.id,
        "510300",
        OrderSide.BUY,
        100,
        Decimal("3.100"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("311.0000"),
        market=Market.HK_CONNECT,
    )
    repo.upsert_daily_bar_diagnostic(trade_date, Market.ETF, "510300", "raw", "missing_exact_date", [], resolved=False)
    repo.upsert_daily_bar_diagnostic(trade_date, Market.ETF, "510500", "qfq", "missing_exact_date", [], resolved=False)
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.A_SHARE, "510300", "qfq", "missing_exact_date", [], resolved=False
    )
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.HK_CONNECT, "510300", "qfq", "missing_exact_date", [], resolved=False
    )

    class MarketData:
        def __init__(self):
            self.daily_bar_calls = []

        def get_daily_bar(self, symbol, requested_date, market=None):
            self.daily_bar_calls.append((symbol, requested_date, market))
            return DailyBar(
                symbol,
                requested_date,
                Decimal("3.100"),
                Decimal("3.200"),
                Decimal("3.000"),
                Decimal("3.100"),
            )

        def get_latest_daily_close(self, symbol, requested_date, market=None):
            return Decimal("3.100")

        def next_trade_date(self, requested_date):
            return requested_date

    market_data = MarketData()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    app.dependency_overrides[get_market_data_provider] = lambda: market_data

    response = TestClient(app).post("/paper/matching/runs/rebuilds", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {"rebuilt_account_ids": [etf_account.id]}
    assert len(market_data.daily_bar_calls) >= 2
    assert set(market_data.daily_bar_calls) == {("510300", trade_date, Market.ETF)}
    assert repo.get_order(etf_order.id).status == OrderStatus.FILLED.value
    assert repo.get_order(legacy_etf_order.id).status == OrderStatus.ACCEPTED.value
    assert repo.get_order(a_share_order.id).status == OrderStatus.ACCEPTED.value
    assert repo.get_order(hk_order.id).status == OrderStatus.ACCEPTED.value
    refreshed_diagnostic = next(
        item
        for item in repo.list_daily_bar_diagnostics()
        if item.market == Market.ETF.value and item.stock_id == "510300"
    )
    assert refreshed_diagnostic.resolved is True


def test_matching_api_rolls_back_and_hides_persistence_error(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("api-persistence-failure", Decimal("100000.00"))
    rollback_calls = 0

    def fail_commit():
        raise SQLAlchemyError("SELECT secret_column FROM paper_accounts WHERE password='secret'")

    def track_rollback():
        nonlocal rollback_calls
        rollback_calls += 1

    monkeypatch.setattr(sqlite_session, "commit", fail_commit)
    monkeypatch.setattr(sqlite_session, "rollback", track_rollback)

    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    app.dependency_overrides[get_market_data_provider] = object

    response = TestClient(app).post(
        "/paper/matching/runs",
        json={"trade_date": "2026-07-31", "account_id": account.id},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "MATCHING_PERSISTENCE_FAILED",
            "message": "Matching persistence failed",
            "details": {},
        }
    }
    assert rollback_calls == 1
    assert "secret_column" not in response.text
    assert "password" not in response.text


def test_matching_api_rolls_back_per_order_persistence_error(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("api-order-persistence-failure", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 7, 31),
        status=OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1001.0000"),
    )
    rollback_calls = 0

    def fail_create_trade(*args, **kwargs):
        raise SQLAlchemyError("INSERT secret_column password='secret'")

    def track_rollback():
        nonlocal rollback_calls
        rollback_calls += 1

    monkeypatch.setattr(PaperTradingRepository, "create_trade", fail_create_trade)
    monkeypatch.setattr(sqlite_session, "rollback", track_rollback)

    class MarketData:
        def get_daily_bar(self, symbol, trade_date, market=None):
            return DailyBar(symbol, trade_date, Decimal("10"), Decimal("100"), Decimal("1"), Decimal("50"))

    app = create_app()
    app.dependency_overrides[get_market_data_provider] = lambda: MarketData()
    app.dependency_overrides[get_session] = lambda: sqlite_session

    response = TestClient(app).post(
        "/paper/matching/runs",
        json={"trade_date": "2026-07-31", "account_id": account.id},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "MATCHING_PERSISTENCE_FAILED",
            "message": "Matching persistence failed",
            "details": {},
        }
    }
    assert rollback_calls == 1
    assert "secret_column" not in response.text
    assert "password" not in response.text
    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
