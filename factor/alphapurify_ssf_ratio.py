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

from common.const import COL_CLOSE, COL_DATE  # noqa: E402
from factor.alphapurify_ssf_common import (  # noqa: E402
    SSF_FACTOR_RATIO,
    build_ssf_factor_panel_from_db,
)
from storage import get_storage  # noqa: E402

try:
    from alphapurify import FactorAnalyzer
except Exception:
    FactorAnalyzer = None


EXIT_OK = 0
EXIT_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 DB 读取社保基金持股比例因子面板并用 Alphapurify 做分析"
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


def load_ssf_ratio_panel_from_db(
    storage: Any,
    start_date: str | None,
    end_date: str | None,
    max_stocks: int,
    adjust: str,
) -> pd.DataFrame:
    # build using a stable factor name expected by downstream analysis
    # build using the canonical factor name from common
    panel: pd.DataFrame = build_ssf_factor_panel_from_db(
        storage=storage,
        factor_name=SSF_FACTOR_RATIO,
        start_date=start_date,
        end_date=end_date,
        max_stocks=max_stocks,
        adjust=adjust,
    )
    if panel.empty:
        return pd.DataFrame()

    df = panel.copy()
    # normalize column names to match other alphapurify scripts
    if COL_DATE in df.columns:
        df = df.rename(columns={COL_DATE: "datetime"})
    if COL_CLOSE in df.columns:
        df = df.rename(columns={COL_CLOSE: "close"})

    # SSF_FACTOR_RATIO now matches the downstream expected name, so no renaming needed
    # but keep the logic to ensure the factor column exists
    if SSF_FACTOR_RATIO not in df.columns:
        raise ValueError(
            f"Expected factor column '{SSF_FACTOR_RATIO}' not found in panel"
        )

    # validate required panel columns before selecting
    required_cols = ["datetime", "symbol", "close", SSF_FACTOR_RATIO]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Missing required panel columns: {missing_cols}. "
            f"FactorAnalyzer requires datetime, symbol, close, and {SSF_FACTOR_RATIO}"
        )

    # select and order columns
    return df.loc[:, required_cols].copy()


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
        factor_name=SSF_FACTOR_RATIO,
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
        panel_df = load_ssf_ratio_panel_from_db(
            storage=storage,
            start_date=args.start_date,
            end_date=args.end_date,
            max_stocks=args.max_stocks,
            adjust=args.adjust,
        )
        if panel_df.empty:
            print("[错误] 未从 DB 构造出有效的社保基金合计持股比例因子面板数据")
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
