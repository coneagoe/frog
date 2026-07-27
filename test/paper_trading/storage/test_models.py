from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from paper_trading.storage.models import (
    PaperPositionLot,
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
