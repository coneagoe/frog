from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session, sessionmaker

from monitor.monitor_target_service import MonitorTargetService
from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_session
from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.models import DailyBarDiagnostic, PaperCashLedger
from paper_trading.storage.repository import PaperTradingRepository
from storage.enum_governance import migrate_enums
from storage.model import Base, BlackroomRecord, SSFChangeSignal, StockMonitorTarget
from storage.storage_db import StorageDb


def _engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    return create_engine(url)


@pytest.fixture()
def postgres_schema() -> Iterator[tuple[Engine, str]]:
    admin_engine = _engine()
    schema = f"enum_governance_smoke_{uuid.uuid4().hex}"
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        migration = migrate_enums(connection)
        assert migration.converted is True
        assert all(audit.missing_tables for audit in migration.audits)
        assert set(
            connection.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
                    "AND tablename IN ('paper_orders', 'stock_monitor_targets', 'blackroom_records', "
                    "'daily_bar_diagnostics', 'ssf_change_signals')"
                )
            ).scalars()
        ) == {
            "paper_orders",
            "stock_monitor_targets",
            "blackroom_records",
            "daily_bar_diagnostics",
            "ssf_change_signals",
        }
    engine = create_engine(admin_engine.url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        yield engine, schema
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


@contextmanager
def _session(engine: Engine, schema: str) -> Iterator[Session]:
    connection = engine.connect()
    connection.execute(text(f'SET search_path TO "{schema}"'))
    session = sessionmaker(bind=connection)()
    try:
        yield session
    finally:
        session.close()
        connection.close()


def _storage(engine: Engine, schema: str) -> StorageDb:
    del schema
    storage = object.__new__(StorageDb)
    storage.engine = engine
    storage.Session = sessionmaker(bind=engine)
    return storage


def _signal_payload() -> dict[str, object]:
    return {
        "stock_id": "000001",
        "ann_date": "2026-06-30",
        "prev_ann_date": "2026-03-31",
        "status": "signal",
        "event_types": ["increase"],
        "score": 1.0,
        "detail_json": {"holders": []},
    }


class _WarningMarketData:
    def __init__(self) -> None:
        self.calls = 0

    def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
        del symbol, trade_date, market
        return None

    def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
        del market
        self.calls += 1
        if self.calls == 1:
            return DailyBar(symbol, trade_date, Decimal("10"), Decimal("100"), Decimal("1"), Decimal("50"))
        raise KeyError(f"No daily bar for {symbol} on {trade_date}")


def test_postgresql_governed_writer_smoke_uses_canonical_labels(postgres_schema, monkeypatch) -> None:
    engine, schema = postgres_schema
    storage = _storage(engine, schema)
    with _session(engine, schema) as session:
        repository = PaperTradingRepository(session)
        account = repository.create_account("enum-smoke", Decimal("100000.00"))
        order = repository.create_order(
            account.id,
            "000001",
            OrderSide.BUY,
            100,
            Decimal("10.00"),
            date(2026, 8, 9),
            OrderStatus.ACCEPTED,
            frozen_cash=Decimal("1005.00"),
        )
        session.commit()
        assert order.side == "buy"
        assert session.query(PaperCashLedger).filter_by(account_id=account.id, event_type="freeze").count() == 1

        monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
        app = create_app()
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[get_market_data_provider] = _WarningMarketData
        response = TestClient(app).post(
            "/paper/matching/runs",
            json={"trade_date": "2026-08-09", "account_id": account.id},
            headers={"Authorization": "Bearer secret"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed_with_warnings"

        target = MonitorTargetService(storage=storage).add_target(
            "600519", "A", {"type": "price_threshold", "direction": "below", "value": 1500}
        )
        assert target["success"] is True
        assert target["data"]["market"] == "A"
        assert target["data"]["frequency"] == "daily"
        assert target["data"]["reset_mode"] == "auto"

        blackroom = storage.create_blackroom_record(stock_code="000001", market="A", source="manual")
        diagnostic = repository.upsert_daily_bar_diagnostic(
            date(2026, 8, 9), "000001", "bfq", "missing_market_data", [], resolved=False
        )
        session.commit()
        signal_ids = storage.save_ssf_change_signals([_signal_payload()])

        assert blackroom.market == "A"
        assert diagnostic.adjust == "bfq"
        assert signal_ids
        assert session.get(BlackroomRecord, blackroom.id).source == "manual"
        assert session.get(DailyBarDiagnostic, diagnostic.id).classification == "missing_market_data"
        assert session.get(SSFChangeSignal, signal_ids[0]).event_types == ["increase"]
        assert session.get(StockMonitorTarget, target["data"]["id"]).frequency == "daily"


def test_postgresql_governed_catalog_contains_writer_enums_and_checks(postgres_schema) -> None:
    engine, schema = postgres_schema
    expected = {
        ("paper_orders", "side", "paper_order_side"),
        ("paper_cash_ledger", "event_type", "paper_cash_event_type"),
        ("paper_matching_runs", "status", "paper_matching_run_status"),
        ("stock_monitor_targets", "market", "monitor_market"),
        ("blackroom_records", "market", "blackroom_market"),
        ("daily_bar_diagnostics", "adjust", "daily_bar_diagnostic_adjust"),
        ("ssf_change_signals", "status", "ssf_change_signal_status"),
    }
    with engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        rows = set(
            connection.execute(
                text(
                    "SELECT c.relname, a.attname, t.typname "
                    "FROM pg_attribute a "
                    "JOIN pg_class c ON c.oid = a.attrelid "
                    "JOIN pg_type t ON t.oid = a.atttypid "
                    "WHERE c.relnamespace = current_schema()::regnamespace "
                    "AND (c.relname, a.attname) IN "
                    "(('paper_orders', 'side'), ('paper_cash_ledger', 'event_type'), "
                    "('paper_matching_runs', 'status'), ('stock_monitor_targets', 'market'), "
                    "('blackroom_records', 'market'), ('daily_bar_diagnostics', 'adjust'), "
                    "('ssf_change_signals', 'status'))"
                )
            ).all()
        )
        checks = set(
            connection.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE connamespace = current_schema()::regnamespace "
                    "AND conname IN ('ck_stock_monitor_targets_condition_type', "
                    "'ck_daily_bar_diagnostics_provider_outcome_status', 'ck_ssf_change_signals_event_types')"
                )
            ).scalars()
        )
    assert rows == expected
    assert checks == {
        "ck_stock_monitor_targets_condition_type",
        "ck_daily_bar_diagnostics_provider_outcome_status",
        "ck_ssf_change_signals_event_types",
    }


@pytest.fixture()
def sqlite_storage() -> Iterator[StorageDb]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    storage = object.__new__(StorageDb)
    storage.engine = engine
    storage.Session = sessionmaker(bind=engine)
    try:
        yield storage
    finally:
        engine.dispose()


def test_sqlite_writer_contract_rejects_invalid_governed_values(sqlite_storage: StorageDb) -> None:
    assert sqlite_storage.save_ssf_change_signals([{**_signal_payload(), "event_types": ["split"]}]) == []
    invalid_target = MonitorTargetService(storage=sqlite_storage).add_target("600519", "A", {"type": "unknown"})
    assert invalid_target["success"] is False
    assert invalid_target["code"] == "VALIDATION_ERROR"
    assert "condition" in invalid_target["message"]
    assert invalid_target["data"] is None
    with pytest.raises(StatementError, match="blackroom_market"):
        sqlite_storage.create_blackroom_record(stock_code="000001", market="US")


def test_sqlite_governed_writers_preserve_canonical_labels(sqlite_storage: StorageDb) -> None:
    blackroom = sqlite_storage.create_blackroom_record(stock_code="000001", market="A", source="manual")
    target = MonitorTargetService(storage=sqlite_storage).add_target(
        "600519", "A", {"type": "price_threshold", "direction": "below", "value": 1500}
    )
    with sqlite_storage.Session() as session:
        diagnostic = PaperTradingRepository(session).upsert_daily_bar_diagnostic(
            date(2026, 8, 9), "000001", "bfq", "missing_market_data", [], resolved=False
        )
        session.commit()
        assert diagnostic.adjust == "bfq"
    signal_ids = sqlite_storage.save_ssf_change_signals([_signal_payload()])

    assert blackroom.market == "A"
    assert target["data"]["market"] == "A"
    assert target["data"]["frequency"] == "daily"
    assert target["data"]["reset_mode"] == "auto"
    assert signal_ids
    with sqlite_storage.Session() as session:
        signal = session.get(SSFChangeSignal, signal_ids[0])
        assert signal is not None
        assert signal.status == "signal"
        assert signal.event_types == ["increase"]
