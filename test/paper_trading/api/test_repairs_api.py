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
from paper_trading.storage.models import PaperOrder
from paper_trading.storage.repository import PaperTradingRepository
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
        return session.get(PaperOrder, order_id)
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
        "repaired_accounts": [
            {"account_id": account_id, "order_ids": [order_id], "replay_start_date": "2026-08-07"}
        ],
        "skipped_accounts": [],
        "failed_accounts": [],
    }
    assert _reload_order(sqlite_factory, order_id).market == Market.ETF.value
