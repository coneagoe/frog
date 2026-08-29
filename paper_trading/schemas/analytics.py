from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from paper_trading.domain.enums import CorporateActionType, MigrationRepairReason


class MetricValue(BaseModel):
    value: Decimal | None = None
    reason: str | None = None


class ActivitySummary(BaseModel):
    total_orders: Decimal
    successful_orders: Decimal
    failed_orders: Decimal


class ActivityAnalytics(BaseModel):
    coverage_start: date
    coverage_end: date
    daily: ActivitySummary
    weekly: ActivitySummary
    monthly: ActivitySummary


class RejectReasonBucket(BaseModel):
    reason: str
    count: int


class OverviewAnalytics(BaseModel):
    total_assets: Decimal | None = None
    cash_available: Decimal | None = None
    market_value: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    net_asset_value: Decimal | None = None
    share_count: Decimal | None = None
    total_return: MetricValue
    simple_asset_return: MetricValue | None = None


class ExecutionAnalytics(BaseModel):
    order_count: int
    filled_count: int
    rejected_count: int
    fill_rate: MetricValue
    rejection_rate: MetricValue
    reject_reasons: list[RejectReasonBucket]


class RoundTripResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    open_trade_date: date
    close_trade_date: date | None
    entry_amount: Decimal
    exit_amount: Decimal
    fees: Decimal
    realized_pnl: Decimal
    return_pct: Decimal | None
    holding_days: int | None
    status: str


class TradeQualityAnalytics(BaseModel):
    closed_count: int
    win_rate: MetricValue
    avg_win: MetricValue
    avg_loss: MetricValue
    payoff_ratio: MetricValue
    profit_factor: MetricValue
    consecutive_wins: int
    consecutive_losses: int
    avg_holding_days: MetricValue
    round_trips: list[RoundTripResponse]


class RiskAnalytics(BaseModel):
    max_drawdown: MetricValue
    current_drawdown: MetricValue
    sharpe: MetricValue
    sortino: MetricValue
    calmar: MetricValue


class ValuationGapResponse(BaseModel):
    trade_date: date
    missing_symbols: list[str]
    details: list[dict[str, Any]]
    resolved: bool


class SnapshotAnalyticsEvent(BaseModel):
    event_type: Literal["snapshot"] = "snapshot"
    id: int
    event_at: datetime
    point_type: str
    quality_status: str
    invalid_reason: str | None = None
    nav: Decimal | None = None
    shares: Decimal | None = None


class CashFlowAnalyticsEvent(BaseModel):
    event_type: Literal["deposit", "withdrawal"]
    id: int
    occurred_at: datetime
    amount: Decimal
    effective_nav: Decimal | None = None
    share_delta: Decimal | None = None


class CorporateActionAnalyticsEvent(BaseModel):
    event_type: Literal["corporate_action"] = "corporate_action"
    id: int
    event_at: datetime
    symbol: str
    action_type: CorporateActionType
    parameters: dict[str, Any]
    impact: dict[str, Any]
    created_at: datetime


AnalyticsEvent = Annotated[
    SnapshotAnalyticsEvent | CashFlowAnalyticsEvent | CorporateActionAnalyticsEvent,
    Field(discriminator="event_type"),
]


class AnalyticsResponse(BaseModel):
    available: Literal[True] = True
    overview: OverviewAnalytics
    activity: ActivityAnalytics | None = None
    execution: ExecutionAnalytics
    trade_quality: TradeQualityAnalytics
    risk: RiskAnalytics
    valuation_gaps: list[ValuationGapResponse]
    event_series: list[AnalyticsEvent]


class AnalyticsUnavailableResponse(BaseModel):
    available: Literal[False] = False
    reason: MigrationRepairReason
