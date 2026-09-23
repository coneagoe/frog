"""Fetch current price and historical OHLCV data for monitor conditions."""

from datetime import date, timedelta
from typing import Iterable, Optional, cast

import numpy as np
import pandas as pd

from common.const import COL_DATE, AdjustType, PeriodType
from common.market_code import Market, to_tushare_code
from common.tushare_client import create_tushare_client
from storage import get_storage

# How many calendar days to fetch per requested trading period
# (conservative: ~2.5× to account for weekends and holidays)
_CALENDAR_MULTIPLIER = 3


def _format_tushare_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _create_tushare_client():
    return create_tushare_client()


def _to_ts_code(stock_code: str, market: str) -> str:
    if market not in ("A", "ETF", "HK"):
        raise ValueError(f"Unknown market: {market}")
    return to_tushare_code(stock_code, cast(Market, market))


def _fetch_a_share_daily_history_from_tushare(
    stock_code: str, start_date: date, end_date: date
) -> Optional[pd.DataFrame]:
    ts_code = _to_ts_code(stock_code, "A")
    pro = _create_tushare_client()

    try:
        df = pro.daily(
            ts_code=ts_code,
            start_date=_format_tushare_date(start_date),
            end_date=_format_tushare_date(end_date),
        )
    except Exception:
        return None

    if df is None or df.empty or "trade_date" not in df.columns or "close" not in df.columns:
        return None

    result = df[["trade_date", "close"]].copy()
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result = result.dropna(subset=["trade_date", "close"])
    if result.empty:
        return None

    result = result.rename(columns={"trade_date": "日期", "close": "收盘"})
    result["日期"] = result["日期"].astype(str)
    return cast(pd.DataFrame, result.sort_values("日期").reset_index(drop=True))


def _fetch_rt_k_map(pro, ts_codes: list[str]) -> dict[str, float]:
    if not ts_codes:
        return {}

    try:
        df = pro.rt_k(ts_code=",".join(ts_codes))
    except Exception:
        return {}

    if df is None or df.empty or "ts_code" not in df.columns or "close" not in df.columns:
        return {}

    series = (
        df[["ts_code", "close"]]
        .dropna(subset=["ts_code", "close"])
        .assign(close=lambda frame: pd.to_numeric(frame["close"], errors="coerce"))
        .dropna(subset=["close"])
        .set_index("ts_code")["close"]
        .astype(float)
    )
    return {str(k): float(v) for k, v in series.to_dict().items()}


def _fetch_rt_hk_k_map(pro, ts_codes: list[str]) -> dict[str, float]:
    if not ts_codes:
        return {}

    result = {}
    for ts_code in ts_codes:
        try:
            df = pro.rt_hk_k(ts_code=ts_code)
        except Exception:
            continue
        if df is None or df.empty or "close" not in df.columns:
            continue
        close = pd.to_numeric(df.iloc[-1]["close"], errors="coerce")
        if pd.notna(close):
            result[ts_code] = float(close)
    return result


def fetch_price_map(items: Iterable[tuple[str, str]]) -> dict[tuple[str, str], float]:
    pairs = list(items)
    result = {(stock_code, market): np.nan for stock_code, market in pairs}
    a_etf_codes: list[str] = []
    hk_codes: list[str] = []
    reverse_lookup: dict[str, list[tuple[str, str]]] = {}

    for stock_code, market in pairs:
        ts_code = _to_ts_code(stock_code, market)  # validates every input before client construction
        reverse_lookup.setdefault(ts_code, []).append((stock_code, market))
        if market == "HK":
            hk_codes.append(ts_code)
        else:
            a_etf_codes.append(ts_code)

    pro = _create_tushare_client()

    for ts_code, price in _fetch_rt_k_map(pro, a_etf_codes).items():
        for pair in reverse_lookup.get(ts_code, ()):
            result[pair] = price

    for ts_code, price in _fetch_rt_hk_k_map(pro, hk_codes).items():
        for pair in reverse_lookup.get(ts_code, ()):
            result[pair] = price

    return result


def fetch_price(stock_code: str, market: Market) -> float:
    price = fetch_price_map([(stock_code, market)]).get((stock_code, market), np.nan)
    if price is None:
        return float(np.nan)
    return float(price)


def fetch_current_price(stock_code: str, market: Market) -> float:
    return fetch_price(stock_code, market)


def fetch_final_close_history_df(stock_code: str, as_of_date: date, min_periods: int) -> Optional[pd.DataFrame]:
    """Load the final close history exclusively from daily HFQ storage."""
    start_day = as_of_date - timedelta(days=min_periods * _CALENDAR_MULTIPLIER)
    df = get_storage().load_history_data_stock(
        stock_id=stock_code,
        period=PeriodType.DAILY,
        adjust=AdjustType.HFQ,
        start_date=start_day.isoformat(),
        end_date=as_of_date.isoformat(),
    )
    if df is None or len(df) < min_periods:
        return None
    return df.sort_values(by=COL_DATE).reset_index(drop=True)


def fetch_history_df(
    stock_code: str,
    market: str,
    min_periods: int = 60,
) -> Optional[pd.DataFrame]:
    """
    Load historical daily close data from storage.

    Args:
        stock_code: Stock/ETF/HK code.
        market: 'A', 'ETF', or 'HK'.
        min_periods: Minimum number of trading rows required; returns None if fewer.

    Returns:
        DataFrame with at least COL_CLOSE column, sorted ascending by date,
        or None if insufficient data.
    """
    # Validate the market and identifier before choosing any history source.
    _to_ts_code(stock_code, market)
    end_day = date.today()
    start_day = end_day - timedelta(days=min_periods * _CALENDAR_MULTIPLIER)

    if market == "A":
        daily_df = _fetch_a_share_daily_history_from_tushare(stock_code, start_day, end_day)
        if daily_df is not None and len(daily_df) >= min_periods:
            return daily_df

    storage = get_storage()
    end_date = end_day.isoformat()
    start_date = start_day.isoformat()

    if market == "ETF":
        df = storage.load_history_data_etf(
            etf_id=stock_code,
            period=PeriodType.DAILY,
            adjust=AdjustType.QFQ,
            start_date=start_date,
            end_date=end_date,
        )
    elif market == "HK":
        df = storage.load_history_data_stock_hk_ggt(
            stock_id=stock_code,
            period=PeriodType.DAILY,
            adjust=AdjustType.QFQ,
            start_date=start_date,
            end_date=end_date,
        )
    else:  # A-share (default)
        df = storage.load_history_data_stock(
            stock_id=stock_code,
            period=PeriodType.DAILY,
            adjust=AdjustType.QFQ,
            start_date=start_date,
            end_date=end_date,
        )

    if df is None or len(df) < min_periods:
        return None

    return df.sort_values(by=df.columns[0]).reset_index(drop=True)
