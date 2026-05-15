#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.const import (  # noqa: E402
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_STOCK_ID,
    AdjustType,
    PeriodType,
)
from factor.obos import COL_OBOS, compute_overbuy_oversell  # noqa: E402
from storage import get_storage  # noqa: E402

try:
    from alphapurify import FactorAnalyzer
except Exception:
    FactorAnalyzer = None


EXIT_OK = 0
EXIT_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 DB 读取 A 股日线数据，计算 OBOS 因子并用 Alphapurify 做分析"
    )
    parser.add_argument(
        "--start-date", default="2024-01-01", help="开始日期 YYYY-MM-DD"
    )
    parser.add_argument("--end-date", default=None, help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--max-stocks", type=int, default=100, help="最多读取多少只股票"
    )
    parser.add_argument(
        "--adjust",
        choices=["qfq", "hfq"],
        default="qfq",
        help="读取 DB 时使用的复权类型",
    )
    parser.add_argument(
        "--report-html", default=None, help="可选：IC 报告 HTML 输出路径"
    )
    return parser


def _normalize_history_df(history_df: pd.DataFrame, stock_id: str) -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame()

    required_cols = [COL_DATE, COL_CLOSE, COL_HIGH, COL_LOW]
    if any(col not in history_df.columns for col in required_cols):
        return pd.DataFrame()

    normalized = history_df[required_cols].copy()
    normalized[COL_DATE] = pd.to_datetime(normalized[COL_DATE], errors="coerce")
    normalized = (
        normalized.dropna(subset=[COL_DATE])
        .sort_values(COL_DATE)
        .reset_index(drop=True)
    )
    if normalized.empty:
        return pd.DataFrame()

    normalized = compute_overbuy_oversell(normalized)
    normalized = normalized.dropna(subset=[COL_OBOS]).copy()
    if normalized.empty:
        return pd.DataFrame()

    normalized["datetime"] = normalized[COL_DATE]
    normalized["symbol"] = stock_id
    normalized["close"] = pd.to_numeric(normalized[COL_CLOSE], errors="coerce")
    normalized = normalized.dropna(subset=["close"]).copy()
    return normalized.loc[:, ["datetime", "symbol", "close", COL_OBOS]].copy()


def load_obos_panel_from_db(
    storage: Any,
    start_date: str | None,
    end_date: str | None,
    max_stocks: int,
    adjust: str,
) -> pd.DataFrame:
    stock_info = storage.load_general_info_stock()
    if stock_info.empty or COL_STOCK_ID not in stock_info.columns:
        return pd.DataFrame(columns=["datetime", "symbol", "close", COL_OBOS])

    adjust_type = AdjustType.QFQ if adjust == "qfq" else AdjustType.HFQ
    stock_ids = (
        stock_info[COL_STOCK_ID]
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .drop_duplicates()
        .head(max_stocks)
        .tolist()
    )

    frames: list[pd.DataFrame] = []
    for stock_id in stock_ids:
        history_df = storage.load_history_data_stock(
            stock_id=stock_id,
            period=PeriodType.DAILY,
            adjust=adjust_type,
            start_date=start_date,
            end_date=end_date,
        )
        panel_piece = _normalize_history_df(history_df, stock_id)
        if not panel_piece.empty:
            frames.append(panel_piece)

    if not frames:
        return pd.DataFrame(columns=["datetime", "symbol", "close", COL_OBOS])

    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(["datetime", "symbol"])
        .reset_index(drop=True)
    )


def run_analysis(
    panel_df: pd.DataFrame,
    report_html: str | None = None,
) -> Any:
    if FactorAnalyzer is None:
        raise ImportError(
            "alphapurify 未安装，请先执行: poetry run pip install alphapurify"
        )

    analyzer = FactorAnalyzer(
        base_df=panel_df,
        trade_date_col="datetime",
        symbol_col="symbol",
        price_col="close",
        factor_name=COL_OBOS,
    )
    analyzer.run()

    if report_html:
        fig = analyzer.create_single_fac_ic_sheet()
        output_path = Path(report_html)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return analyzer


def main(argv: list[str] | None = None, storage: Any | None = None) -> int:
    args = build_parser().parse_args(argv)
    storage = storage or get_storage()

    try:
        panel_df = load_obos_panel_from_db(
            storage=storage,
            start_date=args.start_date,
            end_date=args.end_date,
            max_stocks=args.max_stocks,
            adjust=args.adjust,
        )
        if panel_df.empty:
            print("[错误] 未从 DB 构造出有效的 OBOS 因子面板数据")
            return EXIT_ERROR

        analyzer = run_analysis(panel_df=panel_df, report_html=args.report_html)
    except Exception as exc:
        print(f"[错误] {exc}")
        return EXIT_ERROR

    print(
        f"面板数据: rows={len(panel_df)}, symbols={panel_df['symbol'].nunique()}, dates={panel_df['datetime'].nunique()}"
    )
    if getattr(analyzer, "mean_ics_dict", None) is not None:
        print(f"mean_ics_dict={analyzer.mean_ics_dict}")
    if args.report_html:
        print(f"IC 报告已输出: {args.report_html}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
