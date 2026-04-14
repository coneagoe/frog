"""Condition evaluation engine for stock monitor targets."""

from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from common.const import COL_CLOSE


class ConditionResult(Enum):
    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    INSUFFICIENT_DATA = "insufficient_data"


def _compute_ma(series: pd.Series, period: int) -> float:
    """Return the simple mean of the last `period` values, or NaN if insufficient data."""
    if len(series) < period:
        return np.nan
    return float(series.iloc[-period:].mean())


def _compute_rsi(series: pd.Series, period: int) -> float:
    """Compute Wilder RSI over `period` bars. Returns NaN if insufficient data."""
    if len(series) < period + 1:
        return np.nan
    delta = series.diff().dropna()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    last_gain = float(gain.iloc[-1])
    last_loss = float(loss.iloc[-1])
    if np.isnan(last_gain) or np.isnan(last_loss):
        return np.nan
    if last_loss == 0:
        # All gains, no losses → maximum relative strength
        if last_gain > 0:
            return 100.0
        # Both gains and losses are zero → flat price series → neutral RSI
        return 50.0
    return float(100 - (100 / (1 + last_gain / last_loss)))


def evaluate_condition(
    condition: dict,
    current_price: Optional[float],
    history_df: Optional[pd.DataFrame],
    change_pct: Optional[float] = None,
) -> ConditionResult:
    """
    Evaluate a single condition dict against current market data.

    Args:
        condition: Condition JSON dict (see plan schema).
        current_price: Latest price (intraday real-time or daily close).
        history_df: DataFrame with COL_CLOSE column (historical daily closes).
        change_pct: Pre-computed daily change % (used for 'change_pct' type).

    Returns:
        ConditionResult enum value.
    """
    ctype = condition.get("type")
    direction = condition.get("direction", "above")

    if ctype == "price_threshold":
        threshold = float(condition["value"])
        if current_price is None:
            return ConditionResult.INSUFFICIENT_DATA
        triggered = (
            current_price > threshold
            if direction == "above"
            else current_price < threshold
        )
        return ConditionResult.TRIGGERED if triggered else ConditionResult.NOT_TRIGGERED

    elif ctype == "price_cross_ma":
        period = int(condition["period"])
        if history_df is None or current_price is None or len(history_df) < period:
            return ConditionResult.INSUFFICIENT_DATA
        ma = _compute_ma(history_df[COL_CLOSE], period)
        if np.isnan(ma):
            return ConditionResult.INSUFFICIENT_DATA
        triggered = current_price > ma if direction == "above" else current_price < ma
        return ConditionResult.TRIGGERED if triggered else ConditionResult.NOT_TRIGGERED

    elif ctype == "ma_cross":
        fast = int(condition["fast"])
        slow = int(condition["slow"])
        if history_df is None or len(history_df) < slow:
            return ConditionResult.INSUFFICIENT_DATA
        fast_ma = _compute_ma(history_df[COL_CLOSE], fast)
        slow_ma = _compute_ma(history_df[COL_CLOSE], slow)
        if np.isnan(fast_ma) or np.isnan(slow_ma):
            return ConditionResult.INSUFFICIENT_DATA
        triggered = fast_ma > slow_ma if direction == "golden" else fast_ma < slow_ma
        return ConditionResult.TRIGGERED if triggered else ConditionResult.NOT_TRIGGERED

    elif ctype == "change_pct":
        threshold = float(condition["value"])
        if change_pct is None:
            return ConditionResult.INSUFFICIENT_DATA
        triggered = (
            change_pct > threshold if direction == "above" else change_pct < threshold
        )
        return ConditionResult.TRIGGERED if triggered else ConditionResult.NOT_TRIGGERED

    elif ctype == "rsi":
        period = int(condition.get("period", 14))
        threshold = float(condition["value"])
        if history_df is None or len(history_df) < period + 1:
            return ConditionResult.INSUFFICIENT_DATA
        rsi = _compute_rsi(history_df[COL_CLOSE], period)
        if np.isnan(rsi):
            return ConditionResult.INSUFFICIENT_DATA
        triggered = rsi > threshold if direction == "above" else rsi < threshold
        return ConditionResult.TRIGGERED if triggered else ConditionResult.NOT_TRIGGERED

    else:
        raise ValueError(f"Unknown condition type: {ctype!r}")
