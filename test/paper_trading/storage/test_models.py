from sqlalchemy import create_engine, inspect

from paper_trading.storage.models import (
    tb_name_paper_accounts,
    tb_name_paper_orders,
    tb_name_paper_trades,
)
from storage.model.base import Base


def test_paper_trading_tables_are_registered(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert tb_name_paper_accounts in inspector.get_table_names()
    assert tb_name_paper_orders in inspector.get_table_names()
    assert tb_name_paper_trades in inspector.get_table_names()

    order_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_orders)}
    assert {
        "id",
        "account_id",
        "symbol",
        "side",
        "quantity",
        "limit_price",
        "status",
        "trade_date",
    } <= order_columns
    engine.dispose()
