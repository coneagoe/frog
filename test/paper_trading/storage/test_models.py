from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Boolean, create_engine, inspect
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from paper_trading.domain.enums import MatchingRunStatus
from paper_trading.storage.models import (
    DailyBarDiagnostic,
    PaperMatchingRun,
    PaperPositionLot,
    tb_name_daily_bar_diagnostics,
    tb_name_paper_accounts,
    tb_name_paper_orders,
    tb_name_paper_trade_validity_checks,
    tb_name_paper_trades,
)
from storage.model.base import Base


def test_position_lot_market_defaults_to_a_share(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        lot = PaperPositionLot(
            account_id=1,
            symbol="000001",
            buy_trade_date=date(2026, 7, 27),
            original_quantity=100,
            remaining_quantity=100,
            cost_price=Decimal("10.00"),
        )
        session.add(lot)
        session.flush()
        assert lot.market == "a_share"

    market_column = PaperPositionLot.__table__.c.market
    assert market_column.nullable is False
    assert market_column.server_default is not None
    engine.dispose()


def test_paper_trading_tables_are_registered(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert tb_name_paper_accounts in inspector.get_table_names()
    assert tb_name_paper_orders in inspector.get_table_names()
    assert tb_name_paper_trades in inspector.get_table_names()
    assert tb_name_paper_trade_validity_checks in inspector.get_table_names()
    assert tb_name_daily_bar_diagnostics in inspector.get_table_names()

    order_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_orders)}
    assert {"validity_status", "validity_reason", "validity_checked_at", "comment"} <= order_columns

    trade_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_trades)}
    assert "comment" in trade_columns

    check_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_trade_validity_checks)}
    assert {
        "id",
        "order_id",
        "account_id",
        "symbol",
        "trade_date",
        "side",
        "input_price",
        "daily_low",
        "daily_high",
        "limit_up_price",
        "limit_down_price",
        "touched_limit_up",
        "touched_limit_down",
        "price_in_range",
        "status",
        "reason_code",
        "reason_detail",
        "data_granularity",
        "created_at",
    } <= check_columns
    engine.dispose()


def test_daily_bar_diagnostic_has_business_key_and_json_outcomes():
    assert DailyBarDiagnostic.__table__.primary_key.columns.keys() == ["id"]
    assert {column.name for column in DailyBarDiagnostic.__table__.columns} >= {
        "business_date",
        "stock_id",
        "adjust",
        "classification",
        "provider_outcomes",
        "first_observed_at",
        "last_observed_at",
        "resolved",
    }
    assert any(
        constraint.name == "uq_daily_bar_diagnostics_business_key"
        and {column.name for column in constraint.columns} == {"business_date", "stock_id", "adjust"}
        for constraint in DailyBarDiagnostic.__table__.constraints
    )


def test_daily_bar_diagnostic_resolved_has_postgresql_boolean_default():
    resolved = DailyBarDiagnostic.__table__.c.resolved
    assert isinstance(resolved.type, Boolean)
    assert str(resolved.server_default.arg) == "false"
    ddl = str(CreateTable(DailyBarDiagnostic.__table__).compile(dialect=dialect()))
    assert "resolved BOOLEAN DEFAULT false NOT NULL" in ddl


def test_matching_run_status_round_trips_lowercase_enum_value(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        run = PaperMatchingRun(trade_date=date(2026, 7, 31), status=MatchingRunStatus.RUNNING.value)
        session.add(run)
        session.commit()
        session.expire_all()

        loaded = session.get(PaperMatchingRun, run.id)
        assert loaded is not None
        assert loaded.status == MatchingRunStatus.RUNNING.value

    engine.dispose()


def test_matching_run_status_rejects_unknown_value(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(PaperMatchingRun(trade_date=date(2026, 7, 31), status="in_progress"))
        with pytest.raises((StatementError, ValueError)):
            session.flush()

    engine.dispose()
