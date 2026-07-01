"""Fetch current price and historical OHLCV data for monitor conditions."""

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Optional, cast

import numpy as np
import pandas as pd

from common.const import AdjustType, PeriodType
from storage import get_storage

# How many calendar days to fetch per requested trading period
# (conservative: ~2.5× to account for weekends and holidays)
_CALENDAR_MULTIPLIER = 3


def _format_tushare_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _env_file_candidates() -> list[Path]:
    return [Path.cwd() / ".env", Path(__file__).resolve().parents[1] / ".env"]


def _read_token_from_env_file() -> str | None:
    for env_file in _env_file_candidates():
        if not env_file.exists():
            continue
        try:
            lines = env_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.strip().removeprefix("export ").strip()
            if name == "TUSHARE_TOKEN":
                return value.strip().strip('"').strip("'") or None
    return None


def _create_tushare_client():
    token = os.getenv("TUSHARE_TOKEN") or _read_token_from_env_file()
    if not token:
        return None

    try:
        import tushare as ts
    except Exception:
        return None

    try:
        return ts.pro_api(token=token)
    except Exception:
        # If pro_api raises during creation, treat as unavailable
        return None


def _to_ts_code(stock_code: str, market: str) -> str | None:
    normalized = stock_code.strip()
    if market == "HK":
        return f"{normalized.zfill(5)}.HK"
    if market == "ETF":
        suffix = ".SH" if normalized.startswith("5") else ".SZ"
        return f"{normalized}{suffix}"
    if market == "A":
        # A-share: 6 and 9 are Shanghai; 5-prefixes are ETF-style and should be handled by market="ETF".
        suffix = ".SH" if normalized.startswith(("6", "9")) else ".SZ"
        return f"{normalized}{suffix}"
    return None


def _fetch_a_share_daily_history_from_tushare(
    stock_code: str, start_date: date, end_date: date
) -> Optional[pd.DataFrame]:
    pro = _create_tushare_client()
    if pro is None:
        return None

    ts_code = _to_ts_code(stock_code, "A")
    if ts_code is None:
        return None

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
    pro = _create_tushare_client()
    if pro is None:
        return result

    a_etf_codes = []
    hk_codes = []
    reverse_lookup = {}

    for stock_code, market in pairs:
        ts_code = _to_ts_code(stock_code, market)
        if ts_code is None:
            continue
        reverse_lookup[ts_code] = (stock_code, market)
        if market == "HK":
            hk_codes.append(ts_code)
        else:
            a_etf_codes.append(ts_code)

    for ts_code, price in _fetch_rt_k_map(pro, a_etf_codes).items():
        result[reverse_lookup[ts_code]] = price

    for ts_code, price in _fetch_rt_hk_k_map(pro, hk_codes).items():
        result[reverse_lookup[ts_code]] = price

    return result


def fetch_price(stock_code: str, market: str) -> float:
    price = fetch_price_map([(stock_code, market)]).get((stock_code, market), np.nan)
    if price is None:
        return float(np.nan)
    return float(price)


def fetch_current_price(stock_code: str, market: str) -> float:
    return fetch_price(stock_code, market)


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
