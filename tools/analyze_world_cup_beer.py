"""
分析青岛啤酒和重庆啤酒在世界杯年的表现
从3月底到世界杯开幕/闭幕的涨跌幅、最大涨幅、最大回撤和胜率统计
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 自动获取项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from common.const import AdjustType, PeriodType  # noqa: E402
from stock.data.access_data import load_history_data_stock  # noqa: E402

# 世界杯信息：(年份, 开幕日期, 闭幕日期)
WORLD_CUP_YEARS = [
    (2010, "2010-06-11", "2010-07-11"),  # 南非世界杯
    (2014, "2014-06-12", "2014-07-13"),  # 巴西世界杯
    (2018, "2018-06-14", "2018-07-15"),  # 俄罗斯世界杯
    (2022, "2022-11-20", "2022-12-18"),  # 卡塔尔世界杯
]


def calculate_period_return(df: pd.DataFrame, start_date: str, end_date: str) -> float:
    """计算期间涨跌幅"""
    mask = (df["日期"] >= start_date) & (df["日期"] <= end_date)
    period_df = df[mask]

    if len(period_df) < 2:
        return float("nan")

    start_price = float(period_df.iloc[0]["开盘"])
    end_price = float(period_df.iloc[-1]["收盘"])
    return (end_price - start_price) / start_price * 100


def calculate_max_gain(df: pd.DataFrame, start_date: str, end_date: str) -> float:
    """计算最大涨幅：从起始日到结束时，期间任意一天的最高收盘价相对于起始价的涨幅"""
    mask = (df["日期"] >= start_date) & (df["日期"] <= end_date)
    period_df = df[mask]

    if len(period_df) < 2:
        return float("nan")

    start_price = float(period_df.iloc[0]["开盘"])
    max_close = float(period_df["收盘"].max())
    return (max_close - start_price) / start_price * 100


def calculate_max_dropdown(df: pd.DataFrame, start_date: str, end_date: str) -> float:
    """计算最大跌幅（最大回撤）：从起始日到结束时，期间任意一天的最低收盘价相对于起始价的跌幅"""
    mask = (df["日期"] >= start_date) & (df["日期"] <= end_date)
    period_df = df[mask]

    if len(period_df) < 2:
        return float("nan")

    start_price = float(period_df.iloc[0]["开盘"])
    min_close = float(period_df["收盘"].min())
    return (min_close - start_price) / start_price * 100


def calculate_daily_win_rate(df: pd.DataFrame, start_date: str, end_date: str) -> float:
    """计算胜率：期间内上涨天数 / 总交易天数"""
    mask = (df["日期"] >= start_date) & (df["日期"] <= end_date)
    period_df = df[mask]

    if len(period_df) == 0:
        return np.nan

    up_days = (period_df["收盘"] > period_df["开盘"]).sum()
    total_days = len(period_df)
    return up_days / total_days * 100


def main():
    # 股票代码: 青岛啤酒 600600, 重庆啤酒 600132
    stocks = {
        "青岛啤酒": "600600",
        "重庆啤酒": "600132",
    }

    start_date = "20100101"
    end_date = "20251231"

    print("=" * 80)
    print("青岛啤酒 & 重庆啤酒 世界杯年表现统计")
    print("统计区间：每年3月底 至 世界杯开幕/闭幕")
    print("=" * 80)

    results = []

    for stock_name, stock_id in stocks.items():
        print(f"\n{'='*40}")
        print(f"{stock_name} (代码: {stock_id})")
        print(f"{'='*40}")

        df = load_history_data_stock(
            security_id=stock_id,
            period=PeriodType.DAILY,
            start_date=start_date,
            end_date=end_date,
            adjust=AdjustType.HFQ,
        )

        if df.empty:
            print(f"无法获取 {stock_name} 数据")
            continue

        df["日期"] = pd.to_datetime(df["日期"])
        df = df.sort_values("日期")

        yearly_returns = []
        yearly_win_rates = []

        for year, cup_start, cup_end in WORLD_CUP_YEARS:
            start_dt = pd.Timestamp(f"{year}-03-31")
            start_open_dt = pd.Timestamp(cup_start)
            end_open_dt = pd.Timestamp(cup_end)

            # 找到实际开始日期（3月31日或之后第一个交易日）
            actual_start = df[df["日期"] >= start_dt]["日期"].min()
            if pd.isna(actual_start):
                print(f"  {year}年: 无法找到3月底后的交易日")
                continue

            # 找到世界杯开幕前的最后一个交易日
            actual_end_open = df[df["日期"] <= start_open_dt]["日期"].max()
            if pd.isna(actual_end_open):
                print(f"  {year}年: 无法找到世界杯开幕前的交易日")
                continue

            # 找到世界杯闭幕前的最后一个交易日
            actual_end_close = df[df["日期"] <= end_open_dt]["日期"].max()
            if pd.isna(actual_end_close):
                print(f"  {year}年: 无法找到世界杯闭幕前的交易日")
                continue

            # 开幕统计
            period_return_open = calculate_period_return(
                df, str(actual_start.date()), str(actual_end_open.date())
            )
            max_gain_open = calculate_max_gain(
                df, str(actual_start.date()), str(actual_end_open.date())
            )
            max_dropdown_open = calculate_max_dropdown(
                df, str(actual_start.date()), str(actual_end_open.date())
            )
            win_rate_open = calculate_daily_win_rate(
                df, str(actual_start.date()), str(actual_end_open.date())
            )

            # 闭幕统计
            period_return_close = calculate_period_return(
                df, str(actual_start.date()), str(actual_end_close.date())
            )
            max_gain_close = calculate_max_gain(
                df, str(actual_start.date()), str(actual_end_close.date())
            )
            max_dropdown_close = calculate_max_dropdown(
                df, str(actual_start.date()), str(actual_end_close.date())
            )
            win_rate_close = calculate_daily_win_rate(
                df, str(actual_start.date()), str(actual_end_close.date())
            )

            start_str = actual_start.strftime("%Y-%m-%d")
            end_open_str = actual_end_open.strftime("%Y-%m-%d")
            end_close_str = actual_end_close.strftime("%Y-%m-%d")

            period_df_open = df[
                (df["日期"] >= actual_start) & (df["日期"] <= actual_end_open)
            ]
            trading_days_open = len(period_df_open)
            up_days_open = (period_df_open["收盘"] > period_df_open["开盘"]).sum()

            period_df_close = df[
                (df["日期"] >= actual_start) & (df["日期"] <= actual_end_close)
            ]
            trading_days_close = len(period_df_close)
            up_days_close = (period_df_close["收盘"] > period_df_close["开盘"]).sum()

            open_msg = (
                f"开幕日: {end_open_str} -> 涨跌幅: {period_return_open:+.2f}%, "
                f"最大涨幅: {max_gain_open:+.2f}%, 最大回撤: {max_dropdown_open:+.2f}%, "
                f"日胜率: {win_rate_open:.1f}% ({up_days_open}/{trading_days_open}天)"
            )
            close_msg = (
                f"闭幕日: {end_close_str} -> 涨跌幅: {period_return_close:+.2f}%, "
                f"最大涨幅: {max_gain_close:+.2f}%, 最大回撤: {max_dropdown_close:+.2f}%, "
                f"日胜率: {win_rate_close:.1f}% ({up_days_close}/{trading_days_close}天)"
            )
            print(f"  {year}年世界杯:")
            print(f"    起始日: {start_str}")
            print(f"    {open_msg}")
            print(f"    {close_msg}")

            yearly_returns.append(period_return_close)
            yearly_win_rates.append(win_rate_close)

            results.append(
                {
                    "股票": stock_name,
                    "年份": year,
                    "起始日": start_str,
                    "开幕日": end_open_str,
                    "闭幕日": end_close_str,
                    "开幕涨跌幅(%)": period_return_open,
                    "开幕最大涨幅(%)": max_gain_open,
                    "开幕最大回撤(%)": max_dropdown_open,
                    "开幕日胜率(%)": win_rate_open,
                    "闭幕涨跌幅(%)": period_return_close,
                    "闭幕最大涨幅(%)": max_gain_close,
                    "闭幕最大回撤(%)": max_dropdown_close,
                    "闭幕日胜率(%)": win_rate_close,
                }
            )

        if yearly_returns:
            avg_return = np.nanmean(yearly_returns)
            avg_win_rate = np.nanmean(yearly_win_rates)
            print("\n  四年平均:")
            print(f"    平均涨跌幅: {avg_return:+.2f}%")
            print(f"    平均日胜率: {avg_win_rate:.1f}%")

            positive_years = sum(1 for r in yearly_returns if r > 0)
            year_win_rate = positive_years / len(yearly_returns) * 100
            print(
                f"    年份胜率: {year_win_rate:.0f}% ({positive_years}/{len(yearly_returns)}年正收益)"
            )

    # 汇总对比
    print("\n" + "=" * 80)
    print("汇总对比")
    print("=" * 80)

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        pivot_return_open = result_df.pivot(
            index="年份", columns="股票", values="开幕涨跌幅(%)"
        )
        pivot_max_gain_open = result_df.pivot(
            index="年份", columns="股票", values="开幕最大涨幅(%)"
        )
        pivot_max_dd_open = result_df.pivot(
            index="年份", columns="股票", values="开幕最大回撤(%)"
        )
        pivot_win_rate_open = result_df.pivot(
            index="年份", columns="股票", values="开幕日胜率(%)"
        )

        pivot_return_close = result_df.pivot(
            index="年份", columns="股票", values="闭幕涨跌幅(%)"
        )
        pivot_max_gain_close = result_df.pivot(
            index="年份", columns="股票", values="闭幕最大涨幅(%)"
        )
        pivot_max_dd_close = result_df.pivot(
            index="年份", columns="股票", values="闭幕最大回撤(%)"
        )
        pivot_win_rate_close = result_df.pivot(
            index="年份", columns="股票", values="闭幕日胜率(%)"
        )

        print("\n【开幕统计】")
        print("\n各年开幕涨跌幅(%):")
        print(pivot_return_open.to_string())
        print("\n各年开幕最大涨幅(%):")
        print(pivot_max_gain_open.to_string())
        print("\n各年开幕最大回撤(%):")
        print(pivot_max_dd_open.to_string())
        print("\n各年开幕日胜率(%):")
        print(pivot_win_rate_open.to_string())
        print("\n开幕平均涨跌幅(%):")
        print(pivot_return_open.mean().to_string())
        print("\n开幕平均最大涨幅(%):")
        print(pivot_max_gain_open.mean().to_string())
        print("\n开幕平均最大回撤(%):")
        print(pivot_max_dd_open.mean().to_string())
        print("\n开幕平均日胜率(%):")
        print(pivot_win_rate_open.mean().to_string())

        print("\n【闭幕统计】")
        print("\n各年闭幕涨跌幅(%):")
        print(pivot_return_close.to_string())
        print("\n各年闭幕最大涨幅(%):")
        print(pivot_max_gain_close.to_string())
        print("\n各年闭幕最大回撤(%):")
        print(pivot_max_dd_close.to_string())
        print("\n各年闭幕日胜率(%):")
        print(pivot_win_rate_close.to_string())
        print("\n闭幕平均涨跌幅(%):")
        print(pivot_return_close.mean().to_string())
        print("\n闭幕平均最大涨幅(%):")
        print(pivot_max_gain_close.mean().to_string())
        print("\n闭幕平均最大回撤(%):")
        print(pivot_max_dd_close.mean().to_string())
        print("\n闭幕平均日胜率(%):")
        print(pivot_win_rate_close.mean().to_string())

        result_df.to_csv(
            "world_cup_beer_analysis.csv", index=False, encoding="utf-8-sig"
        )
        print("\n结果已保存到 world_cup_beer_analysis.csv")


if __name__ == "__main__":
    main()
