import argparse
import os
import sys

import backtrader as bt
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import conf  # noqa: E402
from backtest.bt_common import run  # noqa: E402
from common.const import (  # noqa: E402
    COL_DATE,
    COL_IPO_DATE,
    COL_IS_ST,
    COL_PB,
    COL_PE,
    COL_STOCK_ID,
    COL_TOTAL_MV,
    SecurityType,
)
from storage import get_storage  # noqa: E402
from storage import (  # noqa: E402
    tb_name_a_stock_basic,
    tb_name_daily_basic_a_stock,
    tb_name_history_data_daily_a_stock_hfq,
)

conf.parse_config()


def load_all_stocks(start_date: str, end_date: str) -> list:
    """加载所有A股股票（排除北交所和回测期间未上市的股票）

    Args:
        start_date: 回测开始日期 (YYYY-MM-DD)
        end_date: 回测结束日期 (YYYY-MM-DD)

    Returns:
        list: 股票代码列表
    """
    storage = get_storage()

    sql = f"""
    SELECT "{COL_STOCK_ID}" FROM {tb_name_a_stock_basic}
    WHERE "{COL_STOCK_ID}" NOT LIKE '8%%'
    AND "{COL_STOCK_ID}" NOT LIKE '4%%'
    AND "{COL_STOCK_ID}" NOT LIKE '920%%'
    AND "{COL_IPO_DATE}" <= %s::date - INTERVAL '2 years'
    """

    df = pd.read_sql(sql, storage.engine, params=(start_date,))
    return df[COL_STOCK_ID].tolist()


class SmallMarketCapitalStrategy(bt.Strategy):
    params = (
        ("top_n", 50),  # 按市值排序前N只
        ("buy_count", 20),  # 每次买入数量
        ("min_list_days", 730),  # 最少上市天数（约2年）
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
        self.last_month = current_month
        self.last_year = current_year

        # 3、4、12月空仓
        if current_month in (3, 4, 12):
            self.clear_position(current_date)
        else:
            self.rebalance(current_date)

    def clear_position(self, current_date):
        """清仓"""
        date_str = current_date.strftime("%Y-%m-%d")
        print(f"{date_str}: 3/4/12月空仓，清仓")

        for data in self.datas:
            pos = self.broker.getposition(data)
            if pos.size != 0:
                self.order_target_percent(data, target=0.0)

    def rebalance(self, current_date):
        """调仓逻辑"""
        storage = get_storage()
        date_str = current_date.strftime("%Y-%m-%d")

        # 一次性查询 daily_basic、ST状态、上市日期
        sql = f"""
        SELECT db.*, h."{COL_IS_ST}", b."{COL_IPO_DATE}"
        FROM "{tb_name_daily_basic_a_stock}" db
        LEFT JOIN "{tb_name_history_data_daily_a_stock_hfq}" h
            ON h."{COL_STOCK_ID}" = db."{COL_STOCK_ID}"
            AND h."{COL_DATE}" = %s
        LEFT JOIN "{tb_name_a_stock_basic}" b
            ON b."{COL_STOCK_ID}" = db."{COL_STOCK_ID}"
        WHERE db."{COL_DATE}" = %s
        AND db."{COL_STOCK_ID}" = ANY(%s)
        AND (h."{COL_IS_ST}" IS NULL OR h."{COL_IS_ST}" = 0)
        AND db."{COL_PB}" > 0
        AND db."{COL_PE}" > 0
        """

        df = pd.read_sql(
            sql,
            storage.engine,
            params=(current_date, current_date, self.stock_ids),  # type: ignore[arg-type]
        )

        if df.empty:
            print(f"No stocks pass filter for {date_str}")
            return

        # 确保上市日期是datetime类型
        df[COL_IPO_DATE] = pd.to_datetime(df[COL_IPO_DATE])

        # 计算上市天数并筛选
        df["上市天数"] = (pd.to_datetime(current_date) - df[COL_IPO_DATE]).dt.days
        df = df[df["上市天数"] > self.p.min_list_days]

        if df.empty:
            print(f"No stocks pass listing days filter for {date_str}")
            return

        # 按市值升序排列，取前N只
        df_sorted = df.sort_values(by=COL_TOTAL_MV, ascending=True)
        df_selected = df_sorted.head(self.p.top_n)

        selected_stocks = df_selected[COL_STOCK_ID].tolist()

        print(
            f"{date_str}: 调仓完成，筛选出{len(df)}只股票，"
            f"选择买入{min(self.p.buy_count, len(selected_stocks))}只"
        )

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

    # 获取所有A股股票（排除北交所和回测期间未上市的股票）
    stocks = load_all_stocks(args.start, args.end)

    print(f"Total stocks: {len(stocks)}")

    cerebro = bt.Cerebro()
    cerebro.addstrategy(SmallMarketCapitalStrategy)

    run(
        strategy_name="small_market_capital_2",
        cerebro=cerebro,
        stocks=stocks,
        start_date=args.start,
        end_date=args.end,
        security_type=SecurityType.STOCK,
    )
