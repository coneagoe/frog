import argparse
import os
import sys

import backtrader as bt
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import conf  # noqa: E402
from backtest.bt_common import run  # noqa: E402
from backtest.small_market_capital_common import (  # noqa: E402
    load_daily_basic,
    load_stock_basic,
)
from common.const import (  # noqa: E402
    COL_IPO_DATE,
    COL_PB,
    COL_PE,
    COL_STOCK_ID,
    COL_TOTAL_MV,
    SecurityType,
)
from storage import get_storage, tb_name_a_stock_basic  # noqa: E402

conf.parse_config()


def load_all_stocks() -> list:
    """加载所有A股股票（排除北交所）

    Returns:
        list: 股票代码列表
    """
    storage = get_storage()

    sql = f"""
    SELECT "{COL_STOCK_ID}" FROM {tb_name_a_stock_basic}
    WHERE "{COL_STOCK_ID}" NOT LIKE '8%%'
    AND "{COL_STOCK_ID}" NOT LIKE '4%%'
    AND "{COL_STOCK_ID}" NOT LIKE '920%%'
    """

    df = pd.read_sql(sql, storage.engine)
    return df[COL_STOCK_ID].tolist()


class SmallMarketCapitalStrategy(bt.Strategy):
    params = (
        ("top_n", 50),  # 按市值排序前N只
        ("buy_count", 20),  # 每次买入数量
        ("min_list_days", 500),  # 最少上市天数（约1年半）
    )

    def __init__(self):
        self.stock_ids = [d._name for d in self.datas]
        self.last_month = None
        self.last_year = None
        self.last_date = None

    def next(self):
        current_date = self.datas[0].datetime.date(0)
        self.last_date = current_date

        # 检查是否是每月的第一个交易日
        current_month = current_date.month
        current_year = current_date.year

        if self.last_month == current_month and self.last_year == current_year:
            return

        # 检查是否是该月的第一天（考虑周末）
        # 如果是本月第一个bar，进行调仓
        self.last_month = current_month
        self.last_year = current_year

        self.rebalance(current_date)

    def rebalance(self, current_date):
        """调仓逻辑"""
        date_str = current_date.strftime("%Y-%m-%d")

        # 获取当前日期的daily_basic数据
        df_daily_basic = load_daily_basic(date_str, self.stock_ids)

        if df_daily_basic.empty:
            print(f"No daily_basic data for {date_str}")
            return

        # 获取股票基本信息（上市日期）
        df_basic = load_stock_basic(self.stock_ids)
        df_basic[COL_IPO_DATE] = pd.to_datetime(df_basic[COL_IPO_DATE], format="%Y%m%d")

        # 筛选条件
        df_filtered = df_daily_basic[
            (df_daily_basic[COL_PB] > 0) & (df_daily_basic[COL_PE] > 0)
        ]

        if df_filtered.empty:
            print(f"No stocks pass PB/PE filter for {date_str}")
            return

        # 合并上市日期信息
        df_filtered = pd.merge(
            df_filtered,
            df_basic[[COL_STOCK_ID, COL_IPO_DATE]],
            on=COL_STOCK_ID,
            how="inner",
        )

        # 计算上市天数并筛选
        df_filtered["上市天数"] = (
            current_date - df_filtered[COL_IPO_DATE].dt.date
        ).dt.days

        df_filtered = df_filtered[df_filtered["上市天数"] > self.p.min_list_days]

        if df_filtered.empty:
            print(f"No stocks pass listing days filter for {date_str}")
            return

        # 按市值升序排列，取前N只
        df_sorted = df_filtered.sort_values(by=COL_TOTAL_MV, ascending=True)
        df_selected = df_sorted.head(self.p.top_n)

        selected_stocks = df_selected[COL_STOCK_ID].tolist()

        # 先清仓
        for data in self.datas:
            pos = self.broker.getposition(data)
            if pos.size != 0:
                self.order_target_percent(data, target=0.0)

        # 买入选中的股票（等权重）
        target_weight = 1.0 / self.p.buy_count

        for stock in selected_stocks[: self.p.buy_count]:
            # 找到对应的data
            for data in self.datas:
                if data._name == stock:
                    self.order_target_percent(data, target=target_weight)
                    break

        print(
            f"{date_str}: 调仓完成，筛选出{len(df_filtered)}只股票，"
            f"选择买入{min(self.p.buy_count, len(selected_stocks))}只"
        )

    def stop(self):
        print(f"Ending Value: {self.broker.getvalue():.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s", "--start", required=True, help="Start date in YYYY-MM-DD format"
    )
    parser.add_argument(
        "-e", "--end", required=True, help="End date in YYYY-MM-DD format"
    )
    args = parser.parse_args()

    # 获取所有A股股票（排除北交所）
    stocks = load_all_stocks()

    print(f"Total stocks: {len(stocks)}")

    cerebro = bt.Cerebro()
    cerebro.addstrategy(SmallMarketCapitalStrategy)

    run(
        strategy_name="small_market_capital",
        cerebro=cerebro,
        stocks=stocks,
        start_date=args.start,
        end_date=args.end,
        security_type=SecurityType.STOCK,
    )
