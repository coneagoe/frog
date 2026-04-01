#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dump 上市公司股东人数（全量历史）

接口: stk_holdernumber（需要 600 积分）
文档: https://tushare.pro/document/2?doc_id=166

用法示例:
    poetry run python tools/dump_stk_holdernumber.py -c 600600.SH
    poetry run python tools/dump_stk_holdernumber.py -c 600600.SH -s 20200101 -e 20260101
    poetry run python tools/dump_stk_holdernumber.py -c 600600.SH --csv
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from download.dl.downloader_tushare import download_stk_holdernumber  # noqa: E402


def dump(
    ts_code: str, start_date: str = "", end_date: str = "", export_csv: bool = False
) -> None:
    print(f"[股东人数] 股票代码: {ts_code}")
    if start_date or end_date:
        print(f"           日期范围: {start_date or '(最早)'} ~ {end_date or '(最新)'}")
    else:
        print("           日期范围: 全量历史")
    print()

    df: pd.DataFrame = download_stk_holdernumber(
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
    )

    if df is None or df.empty:
        print(
            "[无数据] 未获取到记录，请确认股票代码及 Tushare 积分是否充足（需 600 积分）。"
        )
        return

    df = df.sort_values("end_date").reset_index(drop=True)

    col_widths = {"end_date": 12, "ann_date": 12, "holder_num": 12}
    header = f"{'截止日期':<{col_widths['end_date']}}{'公告日期':<{col_widths['ann_date']}}{'股东户数':>{col_widths['holder_num']}}"
    sep = "-" * (
        col_widths["end_date"] + col_widths["ann_date"] + col_widths["holder_num"]
    )
    print(header)
    print(sep)

    for _, row in df.iterrows():
        end = str(row.get("end_date", ""))
        ann = str(row.get("ann_date", ""))
        num = row.get("holder_num", "")
        num_str = f"{int(num):,}" if pd.notna(num) else "-"
        print(
            f"{end:<{col_widths['end_date']}}{ann:<{col_widths['ann_date']}}{num_str:>{col_widths['holder_num']}}"
        )

    print(sep)
    print(f"共 {len(df)} 条记录")

    if export_csv:
        fname = f"stk_holdernumber_{ts_code.replace('.', '_')}"
        if start_date:
            fname += f"_{start_date}"
        if end_date:
            fname += f"_{end_date}"
        fname += ".csv"
        df.to_csv(fname, index=False, encoding="utf-8-sig")
        print(f"\n[导出] 已保存至: {fname}")


def main() -> None:
    parser = argparse.ArgumentParser(description="dump 上市公司历史股东人数")
    parser.add_argument(
        "-c", "--ts_code", required=True, help="股票代码，如 600600.SH、000001.SZ"
    )
    parser.add_argument(
        "-s", "--start_date", default="", help="起始日期 YYYYMMDD（默认不限，获取全量）"
    )
    parser.add_argument(
        "-e", "--end_date", default="", help="截止日期 YYYYMMDD（默认不限）"
    )
    parser.add_argument("--csv", action="store_true", help="同时导出 CSV 文件")
    args = parser.parse_args()

    if not os.getenv("TUSHARE_TOKEN"):
        print("[错误] 请先设置环境变量 TUSHARE_TOKEN")
        sys.exit(1)

    dump(
        ts_code=args.ts_code,
        start_date=args.start_date,
        end_date=args.end_date,
        export_csv=args.csv,
    )


if __name__ == "__main__":
    main()
