from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_session
from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.models import PaperLedgerRebuild
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


class _MarketData:
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
    payload = response.json()
    assert payload["account_id"] == account.id
    assert payload["start_date"] == "2026-07-17"
    assert payload["status"] == "completed"
    assert payload["trigger_evidence"] == {"source": "api-test"}
    assert payload["regenerated_counts"]["trades"] == 1
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
    assert [trade.id for trade in repo.list_trades(account.id)] == before_trade_ids
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    failed = sqlite_session.query(PaperLedgerRebuild).one()
    assert failed.status == "failed"
    assert failed.trigger_evidence == {"source": "api-failure-test"}
    assert "forced replay failure" in failed.error_details


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
