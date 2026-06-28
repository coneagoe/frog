from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.sql import func

from .base import Base

tb_name_paper_accounts = "paper_accounts"
tb_name_paper_cash_ledger = "paper_cash_ledger"
tb_name_paper_positions = "paper_positions"
tb_name_paper_position_lots = "paper_position_lots"
tb_name_paper_orders = "paper_orders"
tb_name_paper_trades = "paper_trades"
tb_name_paper_position_round_trips = "paper_position_round_trips"
tb_name_paper_account_snapshots = "paper_account_snapshots"
tb_name_paper_matching_runs = "paper_matching_runs"
tb_name_paper_trade_validity_checks = "paper_trade_validity_checks"


class PaperAccount(Base):
    __tablename__ = tb_name_paper_accounts

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    initial_cash = Column(Numeric(20, 4), nullable=False)
    status = Column(String(20), nullable=False, server_default="active")
    base_currency = Column(String(10), nullable=False, server_default="CNY")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperCashLedger(Base):
    __tablename__ = tb_name_paper_cash_ledger

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    event_type = Column(String(20), nullable=False)
    amount = Column(Numeric(20, 4), nullable=False)
    order_id = Column(Integer, nullable=True, index=True)
    trade_id = Column(Integer, nullable=True, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    note = Column(Text, nullable=True)


class PaperPosition(Base):
    __tablename__ = tb_name_paper_positions
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_paper_positions_account_symbol"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    total_quantity = Column(Integer, nullable=False, server_default=text("0"))
    frozen_quantity = Column(Integer, nullable=False, server_default=text("0"))
    cost_amount = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    realized_pnl = Column(Numeric(20, 4), nullable=False, server_default=text("0"))


class PaperPositionLot(Base):
    __tablename__ = tb_name_paper_position_lots

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    buy_trade_date = Column(Date, nullable=False, index=True)
    original_quantity = Column(Integer, nullable=False)
    remaining_quantity = Column(Integer, nullable=False)
    cost_price = Column(Numeric(20, 4), nullable=False)


class PaperOrder(Base):
    __tablename__ = tb_name_paper_orders

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)
    quantity = Column(Integer, nullable=False)
    limit_price = Column(Numeric(20, 4), nullable=False)
    trade_date = Column(Date, nullable=False, index=True)
    status = Column(String(30), nullable=False, index=True)
    filled_quantity = Column(Integer, nullable=False, server_default=text("0"))
    frozen_cash = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    frozen_quantity = Column(Integer, nullable=False, server_default=text("0"))
    idempotency_key = Column(String(100), nullable=True, unique=True)
    rejection_code = Column(String(50), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    validity_status = Column(String(20), nullable=True, index=True)
    validity_reason = Column(String(50), nullable=True)
    validity_checked_at = Column(DateTime(timezone=True), nullable=True)


class PaperTradeValidityCheck(Base):
    __tablename__ = tb_name_paper_trade_validity_checks

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey(f"{tb_name_paper_orders}.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    side = Column(String(10), nullable=False)
    input_price = Column(Numeric(20, 4), nullable=False)
    daily_low = Column(Numeric(20, 4), nullable=True)
    daily_high = Column(Numeric(20, 4), nullable=True)
    limit_up_price = Column(Numeric(20, 4), nullable=True)
    limit_down_price = Column(Numeric(20, 4), nullable=True)
    touched_limit_up = Column(Boolean, nullable=True)
    touched_limit_down = Column(Boolean, nullable=True)
    price_in_range = Column(Boolean, nullable=True)
    status = Column(String(20), nullable=False, index=True)
    reason_code = Column(String(50), nullable=False)
    reason_detail = Column(Text, nullable=True)
    data_granularity = Column(String(20), nullable=False, server_default="daily")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperTrade(Base):
    __tablename__ = tb_name_paper_trades

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey(f"{tb_name_paper_orders}.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(20, 4), nullable=False)
    amount = Column(Numeric(20, 4), nullable=False)
    fees = Column(Numeric(20, 4), nullable=False)
    trade_date = Column(Date, nullable=False, index=True)
    trade_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperPositionRoundTrip(Base):
    __tablename__ = tb_name_paper_position_round_trips

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    open_trade_id = Column(Integer, ForeignKey(f"{tb_name_paper_trades}.id"), nullable=False, index=True)
    close_trade_id = Column(Integer, ForeignKey(f"{tb_name_paper_trades}.id"), nullable=True, index=True)
    open_trade_date = Column(Date, nullable=False, index=True)
    close_trade_date = Column(Date, nullable=True, index=True)
    entry_amount = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    exit_amount = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    fees = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    realized_pnl = Column(Numeric(20, 4), nullable=False, server_default=text("0"))
    return_pct = Column(Numeric(20, 6), nullable=True)
    holding_days = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, server_default="open", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperAccountSnapshot(Base):
    __tablename__ = tb_name_paper_account_snapshots
    __table_args__ = (UniqueConstraint("account_id", "trade_date", name="uq_paper_account_snapshots_account_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    cash_available = Column(Numeric(20, 4), nullable=False)
    cash_frozen = Column(Numeric(20, 4), nullable=False)
    market_value = Column(Numeric(20, 4), nullable=False)
    total_assets = Column(Numeric(20, 4), nullable=False)
    realized_pnl = Column(Numeric(20, 4), nullable=False)
    unrealized_pnl = Column(Numeric(20, 4), nullable=False)
    position_count = Column(Integer, nullable=False)
    order_count = Column(Integer, nullable=False)
    trade_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperMatchingRun(Base):
    __tablename__ = tb_name_paper_matching_runs

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False, index=True)
    account_id = Column(Integer, nullable=True, index=True)
    status = Column(String(20), nullable=False)
    processed_count = Column(Integer, nullable=False, server_default=text("0"))
    filled_count = Column(Integer, nullable=False, server_default=text("0"))
    skipped_count = Column(Integer, nullable=False, server_default=text("0"))
    rejected_count = Column(Integer, nullable=False, server_default=text("0"))
    failed_count = Column(Integer, nullable=False, server_default=text("0"))
    error_details = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
