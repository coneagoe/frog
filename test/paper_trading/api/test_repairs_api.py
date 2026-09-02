from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_session
from paper_trading.domain.enums import Market, OrderSide, OrderStatus
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.models import PaperAccountSnapshot, PaperOrder
from paper_trading.storage.repository import PaperTradingRepository
from paper_trading.storage.repository import canonical_trading_snapshot_event_at
from storage.model.base import Base
from storage.model.etf_basic import ETFBasic
from test.paper_trading.fakes import FakeMarketDataProvider

AUTH_HEADERS = {"Authorization": "Bearer secret"}


class RawEtfBarMarketDataProvider(FakeMarketDataProvider):
    def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
        if symbol == "518880":
            assert market == Market.ETF.value
        return super().get_daily_bar(symbol, trade_date, market)


@pytest.fixture
def sqlite_factory(tmp_path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'repairs_api.db'}")
    Base.metadata.create_all(engine)
    ETFBasic.__table__.create(engine, checkfirst=True)
    return sessionmaker(bind=engine)


@pytest.fixture
def seeded_candidate(sqlite_factory):
    session = sqlite_factory()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("repair", Decimal("100000"))
        session.add(ETFBasic(基金代码="518880", 中文简称="Gold ETF", 交易所="SH", 存续状态="L"))
        order = repo.create_order(
            account.id,
            "518880",
            OrderSide.BUY,
            100,
            Decimal("8.80"),
            date(2026, 8, 7),
            OrderStatus.ACCEPTED,
            frozen_cash=Decimal("885.00"),
        )
        session.commit()
        return account.id, order.id
    finally:
        session.close()


@pytest.fixture
def seeded_snapshot_repair(sqlite_factory):
    session = sqlite_factory()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("repair-snapshot", Decimal("100000"))
        other_account = repo.create_account("other", Decimal("50000"))
        session.add_all(
            [
                PaperAccountSnapshot(
                    account_id=account.id,
                    trade_date=date(2026, 8, 25),
                    event_at=canonical_trading_snapshot_event_at(date(2026, 8, 25)).replace(hour=10),
                    point_type="trading",
                    quality_status="valid",
                    cash_available=Decimal("100000.0000"),
                    cash_frozen=Decimal("0.0000"),
                    market_value=Decimal("0.0000"),
                    total_assets=Decimal("100000.0000"),
                    realized_pnl=Decimal("0.0000"),
                    unrealized_pnl=Decimal("0.0000"),
                    position_count=0,
                    order_count=0,
                    trade_count=0,
                    pending_settlement=Decimal("0.0000"),
                    net_asset_value=Decimal("1.000000"),
                    share_count=Decimal("100000.000000"),
                    cumulative_deposit=Decimal("100000.0000"),
                    cumulative_withdrawal=Decimal("0.0000"),
                    net_cash_flow=Decimal("100000.0000"),
                    event_time_provenance="canonical_utc",
                ),
                PaperAccountSnapshot(
                    account_id=account.id,
                    trade_date=date(2026, 8, 26),
                    event_at=canonical_trading_snapshot_event_at(date(2026, 8, 26)),
                    point_type="trading",
                    quality_status="valid",
                    cash_available=Decimal("100000.0000"),
                    cash_frozen=Decimal("0.0000"),
                    market_value=Decimal("0.0000"),
                    total_assets=Decimal("100000.0000"),
                    realized_pnl=Decimal("0.0000"),
                    unrealized_pnl=Decimal("0.0000"),
                    position_count=0,
                    order_count=0,
                    trade_count=0,
                    pending_settlement=Decimal("0.0000"),
                    net_asset_value=Decimal("1.000000"),
                    share_count=Decimal("100000.000000"),
                    cumulative_deposit=Decimal("100000.0000"),
                    cumulative_withdrawal=Decimal("0.0000"),
                    net_cash_flow=Decimal("100000.0000"),
                    event_time_provenance="canonical_utc",
                ),
                PaperAccountSnapshot(
                    account_id=other_account.id,
                    trade_date=date(2026, 8, 25),
                    event_at=canonical_trading_snapshot_event_at(date(2026, 8, 25)).replace(hour=9),
                    point_type="trading",
                    quality_status="valid",
                    cash_available=Decimal("50000.0000"),
                    cash_frozen=Decimal("0.0000"),
                    market_value=Decimal("0.0000"),
                    total_assets=Decimal("50000.0000"),
                    realized_pnl=Decimal("0.0000"),
                    unrealized_pnl=Decimal("0.0000"),
                    position_count=0,
                    order_count=0,
                    trade_count=0,
                    pending_settlement=Decimal("0.0000"),
                    net_asset_value=Decimal("1.000000"),
                    share_count=Decimal("50000.000000"),
                    cumulative_deposit=Decimal("50000.0000"),
                    cumulative_withdrawal=Decimal("0.0000"),
                    net_cash_flow=Decimal("50000.0000"),
                    event_time_provenance="canonical_utc",
                ),
                PaperAccountSnapshot(
                    account_id=account.id,
                    trade_date=date(2026, 8, 27),
                    event_at=canonical_trading_snapshot_event_at(date(2026, 8, 27)).replace(hour=10),
                    point_type="trading",
                    quality_status="valid",
                    cash_available=Decimal("100000.0000"),
                    cash_frozen=Decimal("0.0000"),
                    market_value=Decimal("0.0000"),
                    total_assets=Decimal("100000.0000"),
                    realized_pnl=Decimal("0.0000"),
                    unrealized_pnl=Decimal("0.0000"),
                    position_count=0,
                    order_count=0,
                    trade_count=0,
                    pending_settlement=Decimal("0.0000"),
                    net_asset_value=Decimal("1.000000"),
                    share_count=Decimal("100000.000000"),
                    cumulative_deposit=Decimal("100000.0000"),
                    cumulative_withdrawal=Decimal("0.0000"),
                    net_cash_flow=Decimal("100000.0000"),
                    event_time_provenance="canonical_utc",
                ),
            ]
        )
        session.commit()
        return account.id, other_account.id
    finally:
        session.close()


def _client(monkeypatch, sqlite_factory, market_data) -> TestClient:
    from paper_trading.api import deps

    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_factory()
    app.dependency_overrides[deps.get_session_factory] = lambda: sqlite_factory
    app.dependency_overrides[get_market_data_provider] = lambda: market_data
    return TestClient(app)


def _reload_order(sqlite_factory, order_id: int) -> PaperOrder:
    session = sqlite_factory()
    try:
        order = session.get(PaperOrder, order_id)
        assert isinstance(order, PaperOrder)
        return order
    finally:
        session.close()


def _reload_snapshot(sqlite_factory, snapshot_id: int) -> PaperAccountSnapshot:
    session = sqlite_factory()
    try:
        snapshot = session.get(PaperAccountSnapshot, snapshot_id)
        assert isinstance(snapshot, PaperAccountSnapshot)
        return snapshot
    finally:
        session.close()


def test_repair_api_requires_token(sqlite_factory):
    response = TestClient(create_app()).post("/paper/repairs/etf-markets")

    assert response.status_code == 401


def test_repair_api_defaults_to_dry_run(monkeypatch, sqlite_factory, seeded_candidate):
    account_id, order_id = seeded_candidate
    response = _client(monkeypatch, sqlite_factory, FakeMarketDataProvider()).post(
        "/paper/repairs/etf-markets", headers=AUTH_HEADERS
    )

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert response.json()["candidates"] == [
        {"account_id": account_id, "order_id": order_id, "symbol": "518880", "trade_date": "2026-08-07"}
    ]
    assert _reload_order(sqlite_factory, order_id).market == Market.A_SHARE.value


def test_repair_snapshot_event_at_requires_token(sqlite_factory):
    response = TestClient(create_app()).post("/paper/repairs/trading-snapshot-event-at")

    assert response.status_code == 401


def test_repair_snapshot_event_at_rejects_inverted_range(monkeypatch, sqlite_factory, seeded_snapshot_repair):
    response = _client(monkeypatch, sqlite_factory, FakeMarketDataProvider()).post(
        "/paper/repairs/trading-snapshot-event-at",
        json={"account_id": seeded_snapshot_repair[0], "start_date": "2026-08-26", "end_date": "2026-08-25"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422


def test_repair_snapshot_event_at_404_for_unknown_account(monkeypatch, sqlite_factory):
    response = _client(monkeypatch, sqlite_factory, FakeMarketDataProvider()).post(
        "/paper/repairs/trading-snapshot-event-at",
        json={"account_id": 9999, "start_date": "2026-08-25"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404


def test_repair_snapshot_event_at_defaults_to_dry_run(monkeypatch, sqlite_factory, seeded_snapshot_repair):
    account_id, other_account_id = seeded_snapshot_repair
    session = sqlite_factory()
    try:
        corrupted_before = (
            session.query(PaperAccountSnapshot)
            .filter_by(account_id=account_id, trade_date=date(2026, 8, 25), point_type="trading")
            .one()
        )
        other_before = (
            session.query(PaperAccountSnapshot)
            .filter_by(account_id=other_account_id, trade_date=date(2026, 8, 25), point_type="trading")
            .one()
        )
        corrupted_before_id = corrupted_before.id
        other_before_id = other_before.id
    finally:
        session.close()

    response = _client(monkeypatch, sqlite_factory, FakeMarketDataProvider()).post(
        "/paper/repairs/trading-snapshot-event-at",
        json={"account_id": account_id, "start_date": "2026-08-25"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    expected_candidate = {
        "snapshot_id": corrupted_before_id,
        "trade_date": "2026-08-25",
        "event_at": "2026-08-25T10:59:59.999999Z",
        "canonical_event_at": "2026-08-25T23:59:59.999999Z",
    }
    assert payload["dry_run"] is True
    assert payload["account_id"] == account_id
    assert payload["start_date"] == "2026-08-25"
    assert payload["end_date"] == "2026-08-25"
    assert payload["matched_count"] == 1
    assert payload["updated_count"] == 0
    assert payload["candidates"] == [expected_candidate]
    assert _reload_snapshot(sqlite_factory, corrupted_before_id).event_at.hour == 10
    assert _reload_snapshot(sqlite_factory, other_before_id).event_at.hour == 9


def test_repair_snapshot_event_at_applies_and_is_idempotent(monkeypatch, sqlite_factory, seeded_snapshot_repair):
    account_id, _ = seeded_snapshot_repair
    client = _client(monkeypatch, sqlite_factory, FakeMarketDataProvider())

    response = client.post(
        "/paper/repairs/trading-snapshot-event-at",
        json={"account_id": account_id, "start_date": "2026-08-27", "apply": True},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["dry_run"] is False
    assert response.json()["matched_count"] == 1
    assert response.json()["updated_count"] == 1

    response2 = client.post(
        "/paper/repairs/trading-snapshot-event-at",
        json={"account_id": account_id, "start_date": "2026-08-27", "apply": True},
        headers=AUTH_HEADERS,
    )
    assert response2.status_code == 200
    assert response2.json()["matched_count"] == 0
    assert response2.json()["updated_count"] == 0


def test_repair_api_applies_and_serializes_outcomes(monkeypatch, sqlite_factory, seeded_candidate):
    account_id, order_id = seeded_candidate
    trade_date = date(2026, 8, 7)
    market_data = RawEtfBarMarketDataProvider(
        {
            ("518880", trade_date): DailyBar(
                "518880", trade_date, Decimal("8.80"), Decimal("8.892"), Decimal("8.774"), Decimal("8.892")
            )
        }
    )

    response = _client(monkeypatch, sqlite_factory, market_data).post(
        "/paper/repairs/etf-markets", json={"apply": True}, headers=AUTH_HEADERS
    )

    candidate = {"account_id": account_id, "order_id": order_id, "symbol": "518880", "trade_date": "2026-08-07"}
    assert response.status_code == 200
    assert response.json() == {
        "dry_run": False,
        "candidates": [candidate],
        "corrected_orders": [candidate],
        "repaired_accounts": [{"account_id": account_id, "order_ids": [order_id], "replay_start_date": "2026-08-07"}],
        "skipped_accounts": [],
        "failed_accounts": [],
    }
    assert _reload_order(sqlite_factory, order_id).market == Market.ETF.value
