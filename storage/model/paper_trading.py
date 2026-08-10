from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.sql import func

from paper_trading.domain.enums import (
    AccountStatus,
    CashEventType,
    ETFEligibilityStatus,
    FeePreset,
    LedgerRebuildStatus,
    Market,
    MatchingRunStatus,
    OrderSide,
    OrderStatus,
    PendingSettlementSource,
    PositionSource,
    RoundTripStatus,
    TradeValidityGranularity,
    TradeValidityStatus,
)
from storage.domain_enums import DailyBarDiagnosticAdjust, DailyBarDiagnosticClassification

from .base import Base
from .orm_compat import Mapped, mapped_column

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
tb_name_paper_pending_settlement = "paper_pending_settlement"
tb_name_daily_bar_diagnostics = "daily_bar_diagnostics"
tb_name_paper_valuation_gaps = "paper_valuation_gaps"
tb_name_paper_ledger_rebuilds = "paper_ledger_rebuilds"
tb_name_paper_etf_eligibility = "paper_etf_eligibility"
ETF_ELIGIBILITY_SYMBOL_CHECK_NAME = "ck_paper_etf_eligibility_symbol_six_ascii_digits"
ETF_ELIGIBILITY_SYMBOL_CHECK_SQL = (
    "length(symbol) = 6 AND length("
    "replace(replace(replace(replace(replace(replace(replace(replace(replace(replace("
    "symbol, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), "
    "'5', ''), '6', ''), '7', ''), '8', ''), '9', '')) = 0"
)


def _value_enum(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        values_callable=lambda enum_type: [member.value for member in enum_type],
        native_enum=True,
        validate_strings=True,
        _create_events=False,
    )


class PaperAccount(Base):
    __tablename__ = tb_name_paper_accounts

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    share_count: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, server_default=text("0"))
    net_asset_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, server_default=text("1"))
    cumulative_deposit: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))
    cumulative_withdrawal: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))
    fee_preset: Mapped[str] = mapped_column(
        _value_enum(FeePreset, "paper_fee_preset"), nullable=False, server_default="a_share"
    )
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, server_default=text("0.0003"))
    min_commission: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("5.00"))
    stamp_duty_rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, server_default=text("0.0005"))
    transfer_fee_rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, server_default=text("0.00001"))
    status: Mapped[str] = mapped_column(
        _value_enum(AccountStatus, "paper_account_status"), nullable=False, server_default="active"
    )
    base_currency: Mapped[str] = mapped_column(String(10), nullable=False, server_default="CNY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    hk_commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    hk_min_commission: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    hk_stamp_duty_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    hk_trading_fee_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    hk_sfc_levy_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    hk_afrc_levy_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    hk_settlement_fee_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)


class PaperCashLedger(Base):
    __tablename__ = tb_name_paper_cash_ledger

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(_value_enum(CashEventType, "paper_cash_event_type"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    trade_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    trade_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    net_asset_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    share_delta: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PaperPosition(Base):
    __tablename__ = tb_name_paper_positions
    __table_args__ = (
        UniqueConstraint("account_id", "market", "symbol", name="uq_paper_positions_account_market_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    frozen_quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cost_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))
    source: Mapped[str] = mapped_column(
        _value_enum(PositionSource, "paper_position_source"), nullable=False, server_default="trade"
    )
    market: Mapped[str] = mapped_column(
        _value_enum(Market, "paper_market"), nullable=False, server_default="a_share", index=True
    )


class PaperPositionLot(Base):
    __tablename__ = tb_name_paper_position_lots

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    buy_trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    original_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    source: Mapped[str] = mapped_column(
        _value_enum(PositionSource, "paper_position_source"), nullable=False, server_default="trade"
    )
    market: Mapped[str] = mapped_column(
        _value_enum(Market, "paper_market"), nullable=False, server_default="a_share", index=True
    )


class PaperOrder(Base):
    __tablename__ = tb_name_paper_orders
    __table_args__ = (
        Index(
            "uq_paper_orders_account_idempotency_key",
            "account_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(_value_enum(OrderSide, "paper_order_side"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(_value_enum(OrderStatus, "paper_order_status"), nullable=False, index=True)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    frozen_cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))
    frozen_quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rejection_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    validity_status: Mapped[str | None] = mapped_column(
        _value_enum(TradeValidityStatus, "paper_trade_validity_status"), nullable=True, index=True
    )
    validity_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    validity_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    market: Mapped[str] = mapped_column(
        _value_enum(Market, "paper_market"), nullable=False, server_default="a_share", index=True
    )


class PaperTradeValidityCheck(Base):
    __tablename__ = tb_name_paper_trade_validity_checks

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{tb_name_paper_orders}.id"), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    side: Mapped[str] = mapped_column(_value_enum(OrderSide, "paper_order_side"), nullable=False)
    input_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    daily_low: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    daily_high: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    limit_up_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    limit_down_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    touched_limit_up: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    touched_limit_down: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    price_in_range: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(
        _value_enum(TradeValidityStatus, "paper_trade_validity_status"), nullable=False, index=True
    )
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_granularity: Mapped[str] = mapped_column(
        _value_enum(TradeValidityGranularity, "paper_trade_validity_granularity"),
        nullable=False,
        server_default="daily",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    market: Mapped[str] = mapped_column(
        _value_enum(Market, "paper_market"), nullable=False, server_default="a_share", index=True
    )


class PaperTrade(Base):
    __tablename__ = tb_name_paper_trades

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{tb_name_paper_orders}.id"), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(_value_enum(OrderSide, "paper_order_side"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    trade_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    market: Mapped[str] = mapped_column(
        _value_enum(Market, "paper_market"), nullable=False, server_default="a_share", index=True
    )


class PaperPositionRoundTrip(Base):
    __tablename__ = tb_name_paper_position_round_trips

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    open_trade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_trades}.id"), nullable=False, index=True
    )
    close_trade_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_trades}.id"), nullable=True, index=True
    )
    open_trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    close_trade_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    entry_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))
    exit_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))
    fees: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))
    return_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    holding_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        _value_enum(RoundTripStatus, "paper_round_trip_status"), nullable=False, server_default="open", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    market: Mapped[str] = mapped_column(
        _value_enum(Market, "paper_market"), nullable=False, server_default="a_share", index=True
    )


class PaperAccountSnapshot(Base):
    __tablename__ = tb_name_paper_account_snapshots
    __table_args__ = (UniqueConstraint("account_id", "trade_date", name="uq_paper_account_snapshots_account_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cash_available: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    cash_frozen: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    total_assets: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    order_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False)
    net_asset_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    share_count: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    cumulative_deposit: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    cumulative_withdrawal: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    net_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    pending_settlement: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperValuationGap(Base):
    __tablename__ = tb_name_paper_valuation_gaps
    __table_args__ = (UniqueConstraint("account_id", "trade_date", name="uq_paper_valuation_gaps_account_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    missing_symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    details: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), index=True)


class PaperMatchingRun(Base):
    __tablename__ = tb_name_paper_matching_runs
    __table_args__ = (
        Index(
            "uq_matching_active_scope",
            "trade_date",
            "scope_key",
            unique=True,
            sqlite_where=text("status = 'running'"),
            postgresql_where=text("status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    account_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    scope_key: Mapped[str] = mapped_column(String(40), nullable=False, default="all")
    status: Mapped[str] = mapped_column(_value_enum(MatchingRunStatus, "paper_matching_run_status"), nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    filled_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperPendingSettlement(Base):
    __tablename__ = tb_name_paper_pending_settlement

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    expected_settle_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    trade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(
        _value_enum(PendingSettlementSource, "paper_pending_settlement_source"), nullable=False
    )
    settled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaperLedgerRebuild(Base):
    __tablename__ = tb_name_paper_ledger_rebuilds

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{tb_name_paper_accounts}.id"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    triggering_order_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        _value_enum(LedgerRebuildStatus, "paper_ledger_rebuild_status"), nullable=False, index=True
    )
    deleted_counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    regenerated_counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ETFEligibility(Base):
    __tablename__ = tb_name_paper_etf_eligibility
    __table_args__ = (
        CheckConstraint(
            ETF_ELIGIBILITY_SYMBOL_CHECK_SQL,
            name=ETF_ELIGIBILITY_SYMBOL_CHECK_NAME,
        ),
    )

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)
    list_status: Mapped[str] = mapped_column(String(10), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_refresh_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        _value_enum(ETFEligibilityStatus, "paper_etf_eligibility_status"),
        nullable=False,
        server_default="unknown",
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DailyBarDiagnostic(Base):
    __tablename__ = tb_name_daily_bar_diagnostics
    __table_args__ = (
        UniqueConstraint("business_date", "market", "stock_id", "adjust", name="uq_daily_bar_diagnostics_business_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    market: Mapped[str] = mapped_column(
        _value_enum(Market, "paper_market"), nullable=False, server_default="a_share", index=True
    )
    stock_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    adjust: Mapped[str] = mapped_column(
        _value_enum(DailyBarDiagnosticAdjust, "daily_bar_diagnostic_adjust"), nullable=False
    )
    classification: Mapped[str] = mapped_column(
        _value_enum(DailyBarDiagnosticClassification, "daily_bar_diagnostic_classification"), nullable=False
    )
    provider_outcomes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), index=True)
