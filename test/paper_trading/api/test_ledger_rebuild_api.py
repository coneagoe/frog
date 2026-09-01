from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_session
from paper_trading.domain.enums import (
    MigrationRepairReason,
    OrderSide,
    OrderStatus,
    PaperOrderEventType,
    ReplayTimeProvenance,
)
from paper_trading.schemas.analytics import AnalyticsResponse
from paper_trading.services.analytics_service import AnalyticsService
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.models import PaperLedgerRebuild
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from test.paper_trading.fakes import MarketDataProviderCompatibility


class _MarketData(MarketDataProviderCompatibility):
    def is_trade_date(self, trade_date: date) -> bool:
        return True

    def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
        return DailyBar(symbol, trade_date, Decimal("10"), Decimal("100"), Decimal("1"), Decimal("50"))

    def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
        return Decimal("50")

    def next_trade_date(self, trade_date: date) -> date:
        return trade_date


def _client(monkeypatch, sqlite_session) -> TestClient:
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    app.dependency_overrides[get_market_data_provider] = lambda: _MarketData()
    return TestClient(app)


def test_account_ledger_rebuild_api_replays_from_requested_date(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("ledger-rebuild-api", Decimal("100000"))
    account.migration_repair_reason = MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN.value
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )

    response = _client(monkeypatch, sqlite_session).post(
        f"/paper/accounts/{account.id}/ledger-rebuilds",
        json={"start_date": "2026-07-17", "trigger_evidence": {"source": "api-test"}},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 200
    refreshed_account = repo.get_account(account.id)
    assert refreshed_account is not None
    payload = response.json()
    assert payload["account_id"] == account.id
    assert payload["start_date"] == "2026-07-17"
    assert payload["status"] == "completed"
    assert payload["trigger_evidence"] == {"source": "api-test"}
    assert payload["regenerated_counts"]["trades"] == 1
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    assert refreshed_account.migration_repair_reason is None


def test_account_ledger_rebuild_api_repairs_legacy_filled_sell_for_valid_analytics(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("legacy-filled-sell-rebuild", Decimal("100000"))
    repo.upsert_position(
        account.id,
        "a_share",
        "002558",
        total_quantity=1100,
        frozen_quantity=0,
        cost_amount=Decimal("11000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        "a_share",
        "002558",
        date(2026, 7, 29),
        1100,
        1100,
        Decimal("10"),
        source="imported",
    )
    order = repo.create_order(
        account.id,
        "002558",
        OrderSide.SELL,
        1100,
        Decimal("15"),
        date(2026, 7, 30),
        OrderStatus.FILLED,
        frozen_quantity=0,
    )
    repo.append_order_event(
        account.id,
        order.id,
        "a_share",
        order.symbol,
        PaperOrderEventType.FILL,
        datetime(2026, 7, 30, 9, 30, tzinfo=timezone.utc),
        quantity_delta=Decimal("-1100"),
        cash_delta=Decimal("16450"),
        idempotency_key=f"order:{order.id}:fill:legacy",
    )

    response = _client(monkeypatch, sqlite_session).post(
        f"/paper/accounts/{account.id}/ledger-rebuilds",
        json={"start_date": "2026-07-30"},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    analytics = AnalyticsService(repo, today_provider=lambda: date(2026, 7, 30)).get_account_analytics(account.id)
    assert isinstance(analytics, AnalyticsResponse)
    assert analytics.available is True
    assert analytics.overview.net_asset_value is not None
    assert analytics.overview.net_asset_value > 0


def test_account_ledger_rebuild_api_repairs_creation_provenance(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("ledger-rebuild-provenance", Decimal("100000"))
    initial_ledger = repo.list_cash_ledger(account.id)[0]
    initial_snapshot = repo.list_snapshots(account.id)[0]
    initial_snapshot.trade_date = date(2026, 7, 23)
    initial_ledger.trade_date = None
    initial_ledger.event_time_provenance = None
    initial_snapshot.event_time_provenance = None
    repo.session.flush()
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )

    response = _client(monkeypatch, sqlite_session).post(
        f"/paper/accounts/{account.id}/ledger-rebuilds",
        json={"start_date": "2026-07-17"},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 200
    assert repo.list_cash_ledger(account.id)[0].event_time_provenance == ReplayTimeProvenance.CANONICAL_UTC.value
    assert repo.list_snapshots(account.id)[0].event_time_provenance == ReplayTimeProvenance.CANONICAL_UTC.value
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value


def test_account_ledger_rebuild_api_returns_404_for_missing_account(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())

    response = _client(monkeypatch, sqlite_session).post(
        "/paper/accounts/999/ledger-rebuilds",
        json={"start_date": "2026-07-17"},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 404
    assert sqlite_session.query(PaperLedgerRebuild).count() == 0


def test_account_ledger_rebuild_api_records_failed_audit_without_partial_rebuild(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("ledger-rebuild-failure", Decimal("100000"))
    account.migration_repair_reason = MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN.value
    initial_ledger = repo.list_cash_ledger(account.id)[0]
    initial_snapshot = repo.list_snapshots(account.id)[0]
    initial_ledger.event_time_provenance = None
    initial_snapshot.event_time_provenance = None
    repo.session.flush()
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    market_data = _MarketData()
    MatchingService(repo, market_data, SnapshotService(repo, market_data)).run(date(2026, 7, 17), account.id)
    before_trade_ids = [trade.id for trade in repo.list_trades(account.id)]

    def fail_match(*args, **kwargs):
        raise RuntimeError("forced replay failure")

    monkeypatch.setattr(MatchingService, "match_order", fail_match)

    response = _client(monkeypatch, sqlite_session).post(
        f"/paper/accounts/{account.id}/ledger-rebuilds",
        json={"start_date": "2026-07-17", "trigger_evidence": {"source": "api-failure-test"}},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 500
    failed_account = repo.get_account(account.id)
    assert failed_account is not None
    assert [trade.id for trade in repo.list_trades(account.id)] == before_trade_ids
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    failed = sqlite_session.query(PaperLedgerRebuild).one()
    assert failed.status == "failed"
    assert failed.trigger_evidence == {"source": "api-failure-test"}
    assert "forced replay failure" in failed.error_details
    assert failed_account.migration_repair_reason == MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN.value
    assert repo.list_cash_ledger(account.id)[0].event_time_provenance is None
    assert repo.list_snapshots(account.id)[0].event_time_provenance is None


def test_account_ledger_rebuild_api_rolls_back_failed_match_outcome(monkeypatch, sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("ledger-rebuild-failed-outcome", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )

    def failed_outcome(*args, **kwargs):
        repo.add_cash_event(account.id, "release", Decimal("1"), order_id=order.id, trade_date=order.trade_date)
        return "failed"

    monkeypatch.setattr(MatchingService, "match_order", failed_outcome)

    response = _client(monkeypatch, sqlite_session).post(
        f"/paper/accounts/{account.id}/ledger-rebuilds",
        json={"start_date": "2026-07-17", "trigger_evidence": {"source": "failed-outcome-test"}},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 500
    assert repo.list_trades(account.id) == []
    assert [event.note for event in repo.list_cash_ledger(account.id)] == ["initial_cash"]
    failed = sqlite_session.query(PaperLedgerRebuild).one()
    assert failed.status == "failed"
    assert "ledger rebuild replay failed" in failed.error_details
