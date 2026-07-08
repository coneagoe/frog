"""
Grid Trading Screener — screen stocks suitable for grid trading strategies.

Provides metrics such as range, volatility, trend efficiency, and a composite
score used to rank candidates into three categories of suitability.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

import pandas as pd


@dataclass
class Candidate:
    """A stock candidate for grid trading."""

    name: str
    code: str


# ═══════════════════════════════════════════════════════════════════════
# Metric helpers
# ═══════════════════════════════════════════════════════════════════════


def _max_drawdown(prices: list[float]) -> float:
    """Compute maximum drawdown as a positive decimal (peak-to-trough)."""
    peak = prices[0]
    max_dd = 0.0
    for p in prices:
        if p > peak:
            peak = p
        dd = (peak - p) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _annual_vol(daily_returns: pd.Series) -> float:
    if len(daily_returns) < 2:
        return 0.0
    return float(daily_returns.std() * math.sqrt(252))


def _trend_efficiency(prices: list[float]) -> float:
    """Kaufman efficiency ratio: net direction / total price movement."""
    if len(prices) < 2:
        return 0.0
    total_movement = sum(abs(prices[i] - prices[i - 1]) for i in range(1, len(prices)))
    if total_movement == 0:
        return 0.0
    direction = abs(prices[-1] - prices[0])
    return direction / total_movement


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════


def calculate_metrics(name: str, code: str, history: pd.DataFrame) -> dict:
    """Compute grid-trading suitability metrics for a single stock.

    Parameters
    ----------
    name : str
        Human-readable name for the stock.
    code : str
        Ticker / instrument code.
    history : pandas.DataFrame
        Daily data with at least columns ``trade_date``, ``close``,
        ``amount``.  Up to the latest 250 rows are used.

    Returns
    -------
    dict
        Keys: ``name``, ``code``, ``latest_date``, ``latest_close``,
        ``range_pct``, ``annual_vol``, ``total_ret``, ``max_drawdown``,
        ``trend_eff``, ``pos``, ``avg_amount_yi``, ``score``,
        ``category``.
    """
    if history.empty:
        return {
            "name": name,
            "code": code,
            "latest_date": "",
            "latest_close": 0.0,
            "range_pct": 0.0,
            "annual_vol": 0.0,
            "total_ret": 0.0,
            "max_drawdown": 0.0,
            "trend_eff": 0.0,
            "pos": 0.0,
            "avg_amount_yi": 0.0,
            "score": -999.0,
            "category": "不优先",
        }

    df = history.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    df.sort_values("trade_date", inplace=True)
    df = df.tail(250).reset_index(drop=True)

    closes = df["close"].tolist()
    amounts = df["amount"].tolist()
    close_arr = df["close"].values

    high = float(df["close"].max())
    low = float(df["close"].min())

    latest_date = str(df["trade_date"].iloc[-1])
    latest_close = float(closes[-1])
    range_pct = (high / low) - 1.0 if low > 0 else 0.0

    daily_returns = pd.Series(close_arr).pct_change().dropna()
    annual_vol_val = _annual_vol(daily_returns)
    total_ret = float(closes[-1] / closes[0] - 1) if closes[0] > 0 else 0.0
    max_dd = _max_drawdown(closes)
    trend_eff = _trend_efficiency(closes)

    # Position within the recent range (0 = at low, 1 = at high)
    pos = (latest_close - low) / (high - low) if high > low else 0.5

    # Tushare daily.amount is reported in 千元; divide by 100000 to get 亿元.
    avg_amount_yi = float(sum(amounts) / len(amounts) / 100_000)

    # Composite score – higher is better for grid trading.
    # Favours: wide range, low trend, ample liquidity.
    score = range_pct * 100 - trend_eff * 50 + min(avg_amount_yi / 2, 10)

    category = "更适合" if score >= 15 else ("可做但谨慎" if score >= 5 else "不优先")

    return {
        "name": name,
        "code": code,
        "latest_date": latest_date,
        "latest_close": latest_close,
        "range_pct": round(range_pct, 4),
        "annual_vol": round(annual_vol_val, 4),
        "total_ret": round(total_ret, 4),
        "max_drawdown": round(max_dd, 4),
        "trend_eff": round(trend_eff, 4),
        "pos": round(pos, 4),
        "avg_amount_yi": round(avg_amount_yi, 2),
        "score": round(score, 2),
        "category": category,
    }


def build_report(
    candidates: list[Candidate],
    fetch_daily: Callable,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Build a screening report for a list of candidates.

    Parameters
    ----------
    candidates : list[Candidate]
        Stocks to evaluate.
    fetch_daily : Callable[[str, str, str], pandas.DataFrame]
        Function ``f(code, start, end)`` that returns a DataFrame with
        columns ``trade_date``, ``close``, ``amount``.
    start_date, end_date : str
        Date range in ``YYYYMMDD`` format.

    Returns
    -------
    pandas.DataFrame
        One row per candidate with all metric columns.
    """
    rows = []
    for cand in candidates:
        history = fetch_daily(cand.code, start_date, end_date)
        rows.append(calculate_metrics(cand.name, cand.code, history))
    return pd.DataFrame(rows)


def parse_candidates(args) -> list[Candidate]:
    """Parse candidates from command-line arguments.

    Inline entries may be ``name=code`` or a bare ``code`` (name defaults
    to the code).  If ``args.input_csv`` is set, rows from that CSV
    (columns ``name``, ``code``) are appended.
    """
    candidates: list[Candidate] = []

    for entry in args.candidates:
        if "=" in entry:
            name, code = entry.split("=", 1)
        else:
            name = entry
            code = entry
        candidates.append(Candidate(name.strip(), code.strip()))

    csv_path = getattr(args, "input_csv", None)
    if csv_path:
        csv_df = pd.read_csv(csv_path)
        for _, row in csv_df.iterrows():
            candidates.append(Candidate(str(row["name"]).strip(), str(row["code"]).strip()))

    return candidates


def resolve_date_range(start_date: str, end_date: str, today: date | None = None) -> tuple[str, str]:
    current_day = today or date.today()
    resolved_end = end_date or current_day.strftime("%Y%m%d")
    resolved_start = start_date or (current_day - timedelta(days=460)).strftime("%Y%m%d")
    return resolved_start, resolved_end


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the grid trading screener."""
    parser = argparse.ArgumentParser(description="网格交易选股筛选器 Grid Trading Screener")
    parser.add_argument("candidates", nargs="*", help="标的物，格式 name=code 或直接 code")
    parser.add_argument("--input-csv", help="从 CSV 文件读取标的物（列: name, code）")
    parser.add_argument("--output-csv", help="将报告写入 CSV 文件")
    parser.add_argument("--start-date", default="", help="起始日期 YYYYMMDD")
    parser.add_argument("--end-date", default="", help="结束日期 YYYYMMDD")
    parser.add_argument(
        "--format",
        choices=["table", "csv"],
        default="table",
        help="输出格式（默认 table）",
    )
    parsed = parser.parse_args(argv)

    # Lazy tushare import inside the CLI entry point.
    import tushare as ts  # type: ignore[import-untyped]

    token = os.environ.get("TUSHARE_TOKEN") or ts.get_token()
    if token:
        ts.set_token(token)
    pro = ts.pro_api()

    def fetch_daily(code: str, start_date: str, end_date: str) -> pd.DataFrame:
        df = pro.daily(ts_code=code, start_date=start_date, end_date=end_date)
        if df.empty:
            return df
        return df[["trade_date", "close", "amount"]]

    candidates = parse_candidates(parsed)
    if not candidates:
        print("No candidates provided.", file=sys.stderr)
        return 1

    start_date, end_date = resolve_date_range(parsed.start_date, parsed.end_date)
    report = build_report(candidates, fetch_daily, start_date, end_date)

    if parsed.output_csv:
        report.to_csv(parsed.output_csv, index=False)
        print(f"Report saved to {parsed.output_csv}")
    elif parsed.format == "csv":
        print(report.to_csv(index=False))
    else:
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 200)
        pd.set_option("display.max_colwidth", 20)
        print(report.to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
