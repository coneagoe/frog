from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_session
from paper_trading.domain.enums import Market, OrderSide, OrderStatus, SnapshotPointType
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.order_delete_service import OrderDeleteService
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.models import PaperLedgerRebuild
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
    assert [row.point_type for row in repo.list_snapshots(account.id)] == [SnapshotPointType.INITIAL.value]
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
    diagnostic = repo.list_daily_bar_diagnostics()[0]
    assert diagnostic.resolved is True


def test_matching_rebuild_api_groups_readable_orders_by_account_and_leaves_unreadable_unresolved(
    monkeypatch, sqlite_session
):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("rebuild-grouping", Decimal("100000.00"))
    other_account = repo.create_account("other-rebuild-grouping", Decimal("100000.00"))
    earliest_order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("100.00"),
        date(2026, 7, 25),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("10005.0000"),
    )
    later_order = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("100.00"),
        date(2026, 7, 27),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("10005.0000"),
    )
    unreadable_order = repo.create_order(
        account.id,
        "000003",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 26),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    other_order = repo.create_order(
        other_account.id,
        "000004",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 26),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    for order in [earliest_order, later_order, unreadable_order, other_order]:
        repo.upsert_daily_bar_diagnostic(
            order.trade_date, Market.A_SHARE, order.symbol, "bfq", "missing_exact_date", [], resolved=False
        )

    class MarketData:
        def get_daily_bar(self, symbol, requested_date, market=None):
            if symbol == "000003":
                raise ValueError("Missing market data field low for 000003")
            return DailyBar(symbol, requested_date, Decimal("10"), Decimal("20"), Decimal("1"), Decimal("10"))

        def get_latest_daily_close(self, symbol, requested_date, market=None):
            return Decimal("10")

        def next_trade_date(self, requested_date):
            return requested_date

    rebuild_calls = []

    def record_rebuild(self, account_id, start_date, triggering_order_ids):
        rebuild_calls.append((account_id, start_date, triggering_order_ids))

    monkeypatch.setattr(OrderDeleteService, "rebuild_account_from", record_rebuild)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    app.dependency_overrides[get_market_data_provider] = lambda: MarketData()

    response = TestClient(app).post("/paper/matching/runs/rebuilds", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {"rebuilt_account_ids": [account.id, other_account.id]}
    assert rebuild_calls == [
        (account.id, earliest_order.trade_date, [earliest_order.id, later_order.id]),
        (other_account.id, other_order.trade_date, [other_order.id]),
    ]
    diagnostics = {(item.stock_id, item.business_date): item for item in repo.list_daily_bar_diagnostics()}
    assert diagnostics[("000001", earliest_order.trade_date)].resolved is True
    assert diagnostics[("000002", later_order.trade_date)].resolved is True
    assert diagnostics[("000004", other_order.trade_date)].resolved is True
    assert diagnostics[("000003", unreadable_order.trade_date)].resolved is False


def test_matching_rebuild_api_real_replay_does_not_block_on_independently_unreadable_bar(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("real-replay-unreadable", Decimal("100000.00"))
    readable_early = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 25),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    unreadable_middle = repo.create_order(
        account.id,
        "000003",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 26),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    readable_late = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 27),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    for order in (readable_early, unreadable_middle, readable_late):
        repo.upsert_daily_bar_diagnostic(
            order.trade_date, Market.A_SHARE, order.symbol, "bfq", "missing_exact_date", [], resolved=False
        )

    class MarketData:
        def get_daily_bar(self, symbol, requested_date, market=None):
            if symbol == "000003":
                raise ValueError("Missing market data field low for 000003")
            return DailyBar(symbol, requested_date, Decimal("10"), Decimal("20"), Decimal("1"), Decimal("10"))

        def get_latest_daily_close(self, symbol, requested_date, market=None):
            return Decimal("10")

        def next_trade_date(self, requested_date):
            return requested_date

    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    app.dependency_overrides[get_market_data_provider] = lambda: MarketData()

    response = TestClient(app).post("/paper/matching/runs/rebuilds", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {"rebuilt_account_ids": [account.id]}
    assert repo.get_order(readable_early.id).status == OrderStatus.FILLED.value
    assert repo.get_order(readable_late.id).status == OrderStatus.FILLED.value
    assert repo.get_order(unreadable_middle.id).status == OrderStatus.ACCEPTED.value
    diagnostics = {(item.stock_id, item.business_date): item for item in repo.list_daily_bar_diagnostics()}
    assert diagnostics[("000001", readable_early.trade_date)].resolved is True
    assert diagnostics[("000002", readable_late.trade_date)].resolved is True
    assert diagnostics[("000003", unreadable_middle.trade_date)].resolved is False


def test_matching_rebuild_api_resolves_successful_account_before_later_account_failure(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    successful_account = repo.create_account("successful-rebuild", Decimal("100000.00"))
    failing_account = repo.create_account("failing-rebuild", Decimal("100000.00"))
    successful_order = repo.create_order(
        successful_account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 25),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    failing_order = repo.create_order(
        failing_account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 26),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    for order in (successful_order, failing_order):
        repo.upsert_daily_bar_diagnostic(
            order.trade_date, Market.A_SHARE, order.symbol, "bfq", "missing_exact_date", [], resolved=False
        )

    class MarketData:
        def get_daily_bar(self, symbol, requested_date, market=None):
            return DailyBar(symbol, requested_date, Decimal("10"), Decimal("20"), Decimal("1"), Decimal("10"))

        def get_latest_daily_close(self, symbol, requested_date, market=None):
            return Decimal("10")

        def next_trade_date(self, requested_date):
            return requested_date

    def rebuild_or_fail(self, account_id, start_date, triggering_order_ids):
        if account_id == failing_account.id:
            raise RuntimeError("second account failed")

    monkeypatch.setattr(OrderDeleteService, "rebuild_account_from", rebuild_or_fail)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    app.dependency_overrides[get_market_data_provider] = lambda: MarketData()

    response = TestClient(app).post("/paper/matching/runs/rebuilds", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 500
    diagnostics = {(item.stock_id, item.business_date): item for item in repo.list_daily_bar_diagnostics()}
    assert diagnostics[("000001", successful_order.trade_date)].resolved is True
    assert diagnostics[("000002", failing_order.trade_date)].resolved is False


def test_matching_rebuild_api_persists_failed_audit(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("rebuild-api-failure", Decimal("100000.00"))
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

    def fail_match(*args, **kwargs):
        raise RuntimeError("delayed rebuild replay failed")

    monkeypatch.setattr(MatchingService, "match_order", fail_match)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    app.dependency_overrides[get_market_data_provider] = lambda: MarketData()

    response = TestClient(app).post("/paper/matching/runs/rebuilds", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "HISTORICAL_LEDGER_REBUILD_FAILED",
            "message": "Historical ledger rebuild failed",
            "details": {"error": "delayed rebuild replay failed"},
        }
    }
    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    failed = sqlite_session.query(PaperLedgerRebuild).one()
    assert failed.status == "failed"
    assert failed.triggering_order_ids == [order.id]
    assert "delayed rebuild replay failed" in failed.error_details


def test_matching_rebuild_api_replays_only_a_share_bfq_missing_date_order(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    trade_date = date(2026, 8, 10)
    bfq_account = repo.create_account("a-share-bfq-rebuild-api", Decimal("100000.00"))
    legacy_etf_account = repo.create_account("etf-qfq-diagnostic", Decimal("100000.00"))
    a_share_account = repo.create_account("a-share-qfq-diagnostic", Decimal("100000.00"))
    hk_account = repo.create_account("hk-qfq-diagnostic", Decimal("100000.00"))
    bfq_order = repo.create_order(
        bfq_account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("3.100"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("311.0000"),
        market=Market.A_SHARE,
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
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.A_SHARE, "000001", "bfq", "missing_exact_date", [], resolved=False
    )
    repo.upsert_daily_bar_diagnostic(trade_date, Market.ETF, "510300", "raw", "missing_exact_date", [], resolved=False)
    repo.upsert_daily_bar_diagnostic(trade_date, Market.ETF, "510500", "qfq", "missing_exact_date", [], resolved=False)
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.A_SHARE, "510300", "qfq", "missing_exact_date", [], resolved=False
    )
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.HK_CONNECT, "00700", "qfq", "missing_exact_date", [], resolved=False
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
    assert response.json() == {"rebuilt_account_ids": [bfq_account.id]}
    assert len(market_data.daily_bar_calls) >= 2
    assert set(market_data.daily_bar_calls) == {("000001", trade_date, Market.A_SHARE)}
    assert repo.get_order(bfq_order.id).status == OrderStatus.FILLED.value
    assert repo.get_order(legacy_etf_order.id).status == OrderStatus.ACCEPTED.value
    assert repo.get_order(a_share_order.id).status == OrderStatus.ACCEPTED.value
    assert repo.get_order(hk_order.id).status == OrderStatus.ACCEPTED.value
    refreshed_diagnostic = next(
        item
        for item in repo.list_daily_bar_diagnostics()
        if item.market == Market.A_SHARE.value and item.stock_id == "000001"
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
