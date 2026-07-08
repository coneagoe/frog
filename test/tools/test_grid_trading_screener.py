import os
import sys
from datetime import date
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import tools.grid_trading_screener as grid_trading_screener  # noqa: E402


def make_daily_df(closes: list[float], amounts: list[float] | None = None) -> pd.DataFrame:
    if amounts is None:
        amounts = [1_000_000.0] * len(closes)
    return pd.DataFrame(
        {
            "trade_date": [f"202601{index + 1:02d}" for index in range(len(closes))],
            "close": closes,
            "amount": amounts,
        }
    )


def test_calculate_metrics_scores_oscillating_liquid_stock_as_suitable():
    history = make_daily_df(
        [10, 11, 9, 10.5, 9.5, 11.5, 10, 12, 10.5, 11],
        [500_000.0] * 10,
    )

    metrics = grid_trading_screener.calculate_metrics("示例", "600000.SH", history)

    assert metrics["name"] == "示例"
    assert metrics["code"] == "600000.SH"
    assert metrics["latest_date"] == "20260110"
    assert metrics["latest_close"] == 11.0
    assert metrics["range_pct"] > 0.30
    assert metrics["trend_eff"] < 0.28
    assert metrics["avg_amount_yi"] == 5.0
    assert metrics["category"] == "更适合"


def test_calculate_metrics_marks_low_volatility_stock_as_not_priority():
    history = make_daily_df([10, 10.05, 10.0, 10.08, 10.04, 10.06])

    metrics = grid_trading_screener.calculate_metrics("低波", "600001.SH", history)

    assert metrics["annual_vol"] < 0.15
    assert metrics["category"] == "不优先"


def test_build_report_uses_candidate_arguments_and_fetcher():
    calls: list[str] = []

    def fetch_daily(code: str, start_date: str, end_date: str) -> pd.DataFrame:
        calls.append(code)
        return make_daily_df([10, 11, 9, 10.5, 9.5, 11.5, 10, 12, 10.5, 11])

    report = grid_trading_screener.build_report(
        [grid_trading_screener.Candidate("示例", "600000.SH")],
        fetch_daily=fetch_daily,
        start_date="20250101",
        end_date="20260101",
    )

    assert calls == ["600000.SH"]
    assert report.loc[0, "name"] == "示例"
    assert report.loc[0, "category"] in {"更适合", "可做但谨慎", "不优先"}


def test_parse_candidates_reads_csv_and_inline_candidates(tmp_path):
    csv_path = tmp_path / "stocks.csv"
    pd.DataFrame({"name": ["药明康德"], "code": ["603259.SH"]}).to_csv(csv_path, index=False)
    args = SimpleNamespace(candidates=["中国神华=601088.SH", "600900.SH"], input_csv=str(csv_path))

    candidates = grid_trading_screener.parse_candidates(args)

    assert candidates == [
        grid_trading_screener.Candidate("中国神华", "601088.SH"),
        grid_trading_screener.Candidate("600900.SH", "600900.SH"),
        grid_trading_screener.Candidate("药明康德", "603259.SH"),
    ]


def test_resolve_date_range_defaults_to_recent_460_calendar_days():
    start_date, end_date = grid_trading_screener.resolve_date_range("", "", today=date(2026, 7, 8))

    assert start_date == "20250404"
    assert end_date == "20260708"
