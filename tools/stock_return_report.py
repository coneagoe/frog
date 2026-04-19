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
    COL_STOCK_ID,
    COL_STOCK_NAME,
    AdjustType,
    PeriodType,
)
from storage import get_storage  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
WEEKLY_LOOKBACK = 5
MONTHLY_LOOKBACK = 20
SORT_OPTIONS = {
    "weekly_asc": ("weekly_return_pct", True),
    "weekly_desc": ("weekly_return_pct", False),
    "monthly_asc": ("monthly_return_pct", True),
    "monthly_desc": ("monthly_return_pct", False),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 CSV 读取股票列表并统计过去一周、一个月涨跌幅"
    )
    parser.add_argument("--input-csv", required=True, help="输入 CSV 文件路径")
    parser.add_argument(
        "--stock-id-column", default="stock_id", help="CSV 中股票代码列名"
    )
    parser.add_argument("--name-column", default="name", help="CSV 中股票名称列名")
    parser.add_argument(
        "--adjust",
        choices=["qfq", "hfq"],
        default="qfq",
        help="从 DB 读取的复权类型，默认 qfq",
    )
    parser.add_argument(
        "--sort-by",
        choices=tuple(SORT_OPTIONS),
        default="weekly_asc",
        help="结果排序方式，默认按周涨幅升序",
    )
    parser.add_argument("--output-csv", default=None, help="可选，导出结果 CSV 路径")
    return parser


def _read_input_csv(
    csv_path: str, stock_id_column: str, name_column: str
) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    if stock_id_column not in df.columns and name_column not in df.columns:
        raise ValueError(f"CSV 必须至少包含一列: {stock_id_column} 或 {name_column}")
    return df


def _build_name_mapping(stock_info: pd.DataFrame) -> dict[str, str]:
    if stock_info.empty:
        return {}

    mapping_df = stock_info[[COL_STOCK_ID, COL_STOCK_NAME]].copy()
    mapping_df[COL_STOCK_ID] = mapping_df[COL_STOCK_ID].astype(str).str.strip()
    mapping_df[COL_STOCK_NAME] = mapping_df[COL_STOCK_NAME].astype(str).str.strip()
    mapping_df = mapping_df[
        (mapping_df[COL_STOCK_ID] != "") & (mapping_df[COL_STOCK_NAME] != "")
    ]
    mapping_df = mapping_df.drop_duplicates(subset=[COL_STOCK_NAME], keep="first")
    return dict(zip(mapping_df[COL_STOCK_NAME], mapping_df[COL_STOCK_ID]))


def _calculate_return(history_df: pd.DataFrame, lookback: int) -> float | None:
    if history_df.empty or len(history_df) <= lookback:
        return None

    closes = pd.to_numeric(history_df[COL_CLOSE], errors="coerce")
    latest_close = closes.iloc[-1]
    base_close = closes.iloc[-(lookback + 1)]
    if pd.isna(latest_close) or pd.isna(base_close) or base_close == 0:
        return None

    return round((latest_close / base_close - 1) * 100, 2)


def _format_for_print(report_df: pd.DataFrame) -> pd.DataFrame:
    printable = report_df.copy()
    for column in ("weekly_return_pct", "monthly_return_pct"):
        printable[column] = printable[column].map(
            lambda value: f"{value:.2f}" if pd.notna(value) else ""
        )
    return printable


def _sort_report(report_df: pd.DataFrame, sort_by: str) -> pd.DataFrame:
    sort_column, ascending = SORT_OPTIONS[sort_by]
    return report_df.sort_values(
        by=sort_column,
        ascending=ascending,
        na_position="last",
        kind="mergesort",
    ).reset_index(drop=True)


def build_report(
    csv_path: str,
    storage: Any,
    stock_id_column: str = "stock_id",
    name_column: str = "name",
    adjust: str = "qfq",
    sort_by: str = "weekly_asc",
) -> pd.DataFrame:
    input_df = _read_input_csv(
        csv_path, stock_id_column=stock_id_column, name_column=name_column
    )

    needs_name_lookup = (
        stock_id_column not in input_df.columns
        or input_df[stock_id_column].astype(str).str.strip().eq("").any()
    )
    name_mapping = (
        _build_name_mapping(storage.load_general_info_stock())
        if needs_name_lookup
        else {}
    )

    adjust_type = AdjustType.QFQ if adjust == "qfq" else AdjustType.HFQ
    rows: list[dict[str, Any]] = []

    for _, row in input_df.iterrows():
        stock_id = (
            row.get(stock_id_column, "").strip()
            if stock_id_column in input_df.columns
            else ""
        )
        stock_name = (
            row.get(name_column, "").strip() if name_column in input_df.columns else ""
        )

        if not stock_id and stock_name:
            stock_id = name_mapping.get(stock_name, "")

        result: dict[str, Any] = {
            "stock_id": stock_id,
            "name": stock_name,
            "latest_date": "",
            "latest_close": None,
            "weekly_return_pct": None,
            "monthly_return_pct": None,
            "status": "",
        }

        if not stock_id:
            result["status"] = "未找到股票代码"
            rows.append(result)
            continue

        history_df = storage.load_history_data_stock(
            stock_id,
            PeriodType.DAILY,
            adjust_type,
        )

        if history_df.empty:
            result["status"] = "无历史数据"
            rows.append(result)
            continue

        sorted_history = history_df.copy()
        sorted_history[COL_DATE] = pd.to_datetime(
            sorted_history[COL_DATE], errors="coerce"
        )
        sorted_history = (
            sorted_history.dropna(subset=[COL_DATE])
            .sort_values(COL_DATE)
            .reset_index(drop=True)
        )

        if sorted_history.empty:
            result["status"] = "无有效日期数据"
            rows.append(result)
            continue

        latest_row = sorted_history.iloc[-1]
        result["latest_date"] = latest_row[COL_DATE].strftime("%Y-%m-%d")
        result["latest_close"] = float(latest_row[COL_CLOSE])
        result["weekly_return_pct"] = _calculate_return(sorted_history, WEEKLY_LOOKBACK)
        result["monthly_return_pct"] = _calculate_return(
            sorted_history, MONTHLY_LOOKBACK
        )

        if result["weekly_return_pct"] is None or result["monthly_return_pct"] is None:
            result["status"] = "历史数据不足"

        rows.append(result)

    return _sort_report(pd.DataFrame(rows), sort_by)


def main(argv: list[str] | None = None, storage: Any | None = None) -> int:
    args = build_parser().parse_args(argv)
    storage = storage or get_storage()

    try:
        report_df = build_report(
            csv_path=args.input_csv,
            storage=storage,
            stock_id_column=args.stock_id_column,
            name_column=args.name_column,
            adjust=args.adjust,
            sort_by=args.sort_by,
        )
    except Exception as exc:
        print(f"[错误] {exc}")
        return EXIT_ERROR

    printable = _format_for_print(report_df)
    print(printable.to_string(index=False))

    if args.output_csv:
        output_path = Path(args.output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"\n已导出到: {output_path}")

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
