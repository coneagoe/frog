from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MetricValue(BaseModel):
    value: Decimal | None = None
    reason: str | None = None


class ActivityBucket(BaseModel):
    period: str
    order_count: int
    trade_count: int
    filled_count: int
    rejected_count: int


class RejectReasonBucket(BaseModel):
    reason: str
    count: int


class OverviewAnalytics(BaseModel):
    total_assets: Decimal | None = None
    cash_available: Decimal | None = None
    market_value: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    total_return: MetricValue


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


class AnalyticsResponse(BaseModel):
    overview: OverviewAnalytics
    activity_daily: list[ActivityBucket]
    activity_weekly: list[ActivityBucket]
    activity_monthly: list[ActivityBucket]
    execution: ExecutionAnalytics
    trade_quality: TradeQualityAnalytics
    risk: RiskAnalytics
