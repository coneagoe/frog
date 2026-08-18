from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

import pandas as pd

from common.const import (
    COL_AMOUNT,
    COL_CLOSE,
    COL_DATE,
    COL_ETF_ESTIMATED_TRADED_PRICE,
    COL_ETF_ID,
    COL_ETF_NET_FLOW_AMOUNT,
    COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
    COL_ETF_NET_SHARE_CHANGE,
    COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
    COL_ETF_TOTAL_SHARE,
    COL_INDEX_CODE,
    COL_INDEX_TURNOVER_AMOUNT,
    COL_VOLUME,
)
from download.etf_index_mapping import prepare_etf_flow_index_context

ETF_SHARE_SIZE_UNIT_TO_SHARES = 10000.0
ETF_DAILY_AMOUNT_UNIT_TO_YUAN = 1000.0
ETF_DAILY_VOLUME_UNIT_TO_SHARES = 100.0
INDEX_TURNOVER_UNIT_TO_YUAN = 1000.0


class ETFNetFlowDiagnosticReason(StrEnum):
    MISSING_MAPPING = "missing_mapping"
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


def _normalize_date(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _rows_by_date(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if df.empty or COL_DATE not in df.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in df.to_dict(orient="records"):
        typed_row = cast(dict[str, Any], row)
        rows[_normalize_date(typed_row[COL_DATE])] = typed_row
    return rows


def _as_optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _diagnostic(
    *,
    etf_code: str,
    trade_date: str | None,
    reason: ETFNetFlowDiagnosticReason,
    message: str,
) -> ETFNetFlowDiagnostic:
    return ETFNetFlowDiagnostic(etf_code=etf_code, trade_date=trade_date, reason=reason, message=message)


def rebuild_etf_net_flow(*, storage: Any, etf_code: str, start_date: str, end_date: str) -> ETFNetFlowRebuildResult:
    context = prepare_etf_flow_index_context(etf_code)
    normalized_etf_code = context.normalized_etf_code or etf_code

    if not context.should_calculate or context.index_ts_code is None:
        return ETFNetFlowRebuildResult(
            etf_code=normalized_etf_code,
            saved_rows=0,
            diagnostics=(
                _diagnostic(
                    etf_code=normalized_etf_code,
                    trade_date=None,
                    reason=ETFNetFlowDiagnosticReason.MISSING_MAPPING,
                    message=context.diagnostic.diagnostic_reason,
                ),
            ),
        )

    share_df = storage.load_etf_share_size(
        normalized_etf_code,
        start_date=start_date,
        end_date=end_date,
        include_prior_effective=True,
    )
    daily_by_date = _rows_by_date(storage.load_etf_daily(normalized_etf_code, start_date=start_date, end_date=end_date))
    turnover_by_date = _rows_by_date(
        storage.load_index_daily_turnover(context.index_ts_code, start_date=start_date, end_date=end_date)
    )

    diagnostics: list[ETFNetFlowDiagnostic] = []
    derived_rows: list[dict[str, Any]] = []
    previous_total_share: float | None = None

    if not share_df.empty and COL_DATE in share_df.columns:
        share_df = share_df.copy()
        share_df[COL_DATE] = pd.to_datetime(share_df[COL_DATE])
        share_df = share_df.sort_values(COL_DATE)

    for share_row in share_df.to_dict(orient="records"):
        trade_date = _normalize_date(share_row[COL_DATE])
        current_total_share = _as_optional_float(share_row.get(COL_ETF_TOTAL_SHARE))
        if trade_date < start_date or trade_date > end_date:
            previous_total_share = current_total_share
            continue

        net_share_change = calculate_net_share_change(current_total_share, previous_total_share)
        if net_share_change is None:
            diagnostics.append(
                _diagnostic(
                    etf_code=normalized_etf_code,
                    trade_date=trade_date,
                    reason=ETFNetFlowDiagnosticReason.MISSING_PRIOR_SHARE,
                    message="missing prior effective ETF total share",
                )
            )
            previous_total_share = current_total_share
            continue

        daily_row = daily_by_date.get(trade_date)
        estimated_price = None
        if daily_row is not None:
            estimated_price = estimate_etf_traded_price(
                _as_optional_float(daily_row.get(COL_AMOUNT)),
                _as_optional_float(daily_row.get(COL_VOLUME)),
                _as_optional_float(daily_row.get(COL_CLOSE)),
            )
        if estimated_price is None:
            diagnostics.append(
                _diagnostic(
                    etf_code=normalized_etf_code,
                    trade_date=trade_date,
                    reason=ETFNetFlowDiagnosticReason.MISSING_ETF_DAILY_PRICE,
                    message="missing ETF daily amount/volume or close price support",
                )
            )
            previous_total_share = current_total_share
            continue

        net_flow_amount = calculate_net_flow_amount(net_share_change, estimated_price)
        turnover_row = turnover_by_date.get(trade_date)
        index_turnover = (
            None if turnover_row is None else _as_optional_float(turnover_row.get(COL_INDEX_TURNOVER_AMOUNT))
        )
        if index_turnover is None:
            diagnostics.append(
                _diagnostic(
                    etf_code=normalized_etf_code,
                    trade_date=trade_date,
                    reason=ETFNetFlowDiagnosticReason.MISSING_INDEX_TURNOVER,
                    message="missing mapped index turnover for trade date",
                )
            )
        elif index_turnover == 0:
            diagnostics.append(
                _diagnostic(
                    etf_code=normalized_etf_code,
                    trade_date=trade_date,
                    reason=ETFNetFlowDiagnosticReason.ZERO_INDEX_TURNOVER,
                    message="mapped index turnover is zero",
                )
            )

        derived_rows.append(
            {
                COL_ETF_ID: normalized_etf_code,
                COL_DATE: trade_date,
                COL_ETF_TOTAL_SHARE: current_total_share,
                COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE: previous_total_share,
                COL_ETF_NET_SHARE_CHANGE: net_share_change,
                COL_ETF_ESTIMATED_TRADED_PRICE: estimated_price,
                COL_ETF_NET_FLOW_AMOUNT: net_flow_amount,
                COL_INDEX_CODE: context.index_ts_code,
                COL_INDEX_TURNOVER_AMOUNT: index_turnover,
                COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO: calculate_flow_turnover_ratio(
                    net_flow_amount, index_turnover
                ),
            }
        )
        previous_total_share = current_total_share

    saved_rows = 0
    if derived_rows and storage.save_etf_net_flow(pd.DataFrame(derived_rows)):
        saved_rows = len(derived_rows)

    return ETFNetFlowRebuildResult(
        etf_code=normalized_etf_code,
        saved_rows=saved_rows,
        diagnostics=tuple(diagnostics),
    )
