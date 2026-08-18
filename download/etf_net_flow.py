from dataclasses import dataclass
from enum import StrEnum

ETF_SHARE_SIZE_UNIT_TO_SHARES = 10000.0
ETF_DAILY_AMOUNT_UNIT_TO_YUAN = 1000.0
ETF_DAILY_VOLUME_UNIT_TO_SHARES = 100.0
INDEX_TURNOVER_UNIT_TO_YUAN = 1000.0


class ETFNetFlowDiagnosticReason(StrEnum):
    MISSING_PRIOR_SHARE = "missing_prior_share"
    MISSING_ETF_DAILY_PRICE = "missing_etf_daily_price"
    MISSING_INDEX_TURNOVER = "missing_index_turnover"
    ZERO_INDEX_TURNOVER = "zero_index_turnover"


@dataclass(frozen=True)
class ETFNetFlowDiagnostic:
    etf_code: str
    trade_date: str | None
    reason: ETFNetFlowDiagnosticReason
    message: str


@dataclass(frozen=True)
class ETFNetFlowRebuildResult:
    etf_code: str
    saved_rows: int
    diagnostics: tuple[ETFNetFlowDiagnostic, ...]


def calculate_net_share_change(current_total_share: float | None, previous_total_share: float | None) -> float | None:
    if current_total_share is None or previous_total_share is None:
        return None
    return current_total_share - previous_total_share


def estimate_etf_traded_price(amount: float | None, volume: float | None, close: float | None) -> float | None:
    if amount is not None and volume is not None and amount > 0 and volume > 0:
        return amount * ETF_DAILY_AMOUNT_UNIT_TO_YUAN / (volume * ETF_DAILY_VOLUME_UNIT_TO_SHARES)
    if close is not None and close > 0:
        return close
    return None


def calculate_net_flow_amount(net_share_change: float, estimated_price: float) -> float:
    return net_share_change * ETF_SHARE_SIZE_UNIT_TO_SHARES * estimated_price


def calculate_flow_turnover_ratio(net_flow_amount: float, index_turnover: float | None) -> float | None:
    if index_turnover is None or index_turnover == 0:
        return None
    return net_flow_amount / (index_turnover * INDEX_TURNOVER_UNIT_TO_YUAN)
