from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_session
from paper_trading.domain.enums import OrderSide, OrderStatus
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
