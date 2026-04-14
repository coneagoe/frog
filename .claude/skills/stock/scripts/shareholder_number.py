#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股东人数查询脚本

接口: stk_holdernumber (需要600积分)
文档: https://tushare.pro/document/2?doc_id=166

Usage:
    poetry run python scripts/shareholder_number.py -c 600600.SH
    poetry run python scripts/shareholder_number.py -c 600600.SH -a
    poetry run python scripts/shareholder_number.py -c 600600.SH -x
"""

import tushare as ts
import pandas as pd
import os
import argparse
from datetime import datetime


def get_shareholder_number(
    ts_code: str,
    start_date: str = None,
    end_date: str = None,
    export_csv: bool = False,
) -> pd.DataFrame | None:
    """
    获取上市公司股东户数数据

    Args:
        ts_code: 股票代码，如 600600.SH、000001.SZ
        start_date: 公告日期范围起始，格式 YYYYMMDD，默认从三年前开始
        end_date: 公告日期范围截止，格式 YYYYMMDD，默认今天
        export_csv: 是否导出为 CSV 文件

    Returns:
        包含股东人数数据的 DataFrame，字段: ts_code, ann_date, end_date, holder_num
    """
    if not ts_code:
        print("[错误] 必须指定股票代码，如 -c 600600.SH")
        return None

    token = os.getenv("TUSHARE_TOKEN") or ts.get_token()
    pro = ts.pro_api(token)

    # 默认时间范围
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    if start_date is None:
        start_date = (datetime.now().replace(year=datetime.now().year - 3)).strftime("%Y%m%d")

    try:
        df = pro.stk_holdernumber(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        df = df.sort_values("end_date").reset_index(drop=True)
        print(f"[OK] 获取股东人数成功，共 {len(df)} 条记录")
        print(f"     股票代码: {ts_code}")
        print(f"     时间范围: {df['end_date'].min()} ~ {df['end_date'].max()}")
        print()

        print(df[["end_date", "ann_date", "holder_num"]].to_string(index=False))

        if export_csv:
            output_path = f"shareholder_number_{ts_code.replace('.', '_')}_{start_date}_{end_date}.csv"
            df.to_csv(output_path, index=False, encoding="utf-8-sig")
            print(f"\n[导出] 已保存至: {output_path}")

        return df

    except Exception as e:
        error_msg = str(e)
        if "请指定正确的接口名" in error_msg or "权限" in error_msg.lower():
            print(f"[错误] 接口权限不足，需要 600 积分")
            print(f"       参考: https://tushare.pro/document/2?doc_id=166")
        else:
            print(f"[错误] 获取失败: {e}")
        return None


def analyze_trend(df: pd.DataFrame) -> None:
    """
    分析股东人数趋势
    """
    if df is None or len(df) == 0:
        return

    print("\n===== 股东人数趋势分析 =====")
    holder_nums = df["holder_num"].values
    dates = df["end_date"].values

    print(f"最新数据 ({dates[-1]}): {holder_nums[-1]:,} 户")

    if len(df) >= 2:
        change = holder_nums[-1] - holder_nums[-2]
        pct = change / holder_nums[-2] * 100
        direction = "↑" if change > 0 else "↓"
        print(f"上期 ({dates[-2]}): {holder_nums[-2]:,} 户 {direction} {abs(change):,} ({pct:+.1f}%)")

    if len(df) >= 4:
        recent = holder_nums[-4:]
        print(f"\n近四个季度股东人数:")
        for d, h in zip(dates[-4:], recent):
            print(f"  {d}: {h:>10,} 户")

        first, last = recent[0], recent[-1]
        total_change = (last - first) / first * 100
        if total_change > 0:
            print(f"\n趋势: 筹码分散，股东数累计增长 {total_change:.1f}%（通常意味着散户入场、机构派发）")
        else:
            print(f"\n趋势: 筹码集中，股东数累计减少 {abs(total_change):.1f}%（通常意味着机构吸筹）")

    max_idx = df["holder_num"].idxmax()
    min_idx = df["holder_num"].idxmin()
    print(f"\n历史最高: {df.loc[max_idx, 'end_date']} {df.loc[max_idx, 'holder_num']:,} 户")
    print(f"历史最低: {df.loc[min_idx, 'end_date']} {df.loc[min_idx, 'holder_num']:,} 户")


def main():
    parser = argparse.ArgumentParser(description="查询上市公司股东人数")
    parser.add_argument(
        "-c", "--ts_code", required=True,
        help="股票代码，如 600600.SH、000001.SZ"
    )
    parser.add_argument(
        "-s", "--start_date", default=None,
        help="开始日期 YYYYMMDD"
    )
    parser.add_argument(
        "-e", "--end_date", default=None,
        help="结束日期 YYYYMMDD"
    )
    parser.add_argument(
        "-x", "--export", action="store_true",
        help="导出为 CSV 文件"
    )
    parser.add_argument(
        "-a", "--analyze", action="store_true",
        help="显示趋势分析"
    )

    args = parser.parse_args()

    df = get_shareholder_number(
        ts_code=args.ts_code,
        start_date=args.start_date,
        end_date=args.end_date,
        export_csv=args.export,
    )

    if args.analyze:
        analyze_trend(df)


if __name__ == "__main__":
    main()
