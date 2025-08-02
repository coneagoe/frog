import logging
import os
import sys
from datetime import date

import pandas as pd
import swifter  # noqa: F401

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf  # noqa: E402
from stock import (  # noqa: E402
    COL_ADJUSTED_STOPLOSS,
    COL_ADJUSTED_TAKE_PROFIT,
    COL_BUYING_PRICE,
    COL_PROFIT_STOPLOSS_RATE,
    COL_RESISTANCE,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_STOPLOSS_PERCENT,
    COL_SUPPORT,
    COL_TAKE_PROFIT_PERCENT,
    calculate_support_resistance,
    fetch_close_price,
)
from utility import send_email  # noqa: E402

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)

conf.parse_config()

percent = 0.995

n = 360
end_date = date.today()
start_date = end_date - pd.Timedelta(days=n)
start_date_ts = start_date.strftime("%Y%m%d")
end_date_ts = end_date.strftime("%Y%m%d")

output_file_name = f"spot_trading_{end_date_ts}.csv"


def calculate_stoploss_takeprofit(df: pd.DataFrame):
    df[COL_ADJUSTED_STOPLOSS] = df[COL_SUPPORT] * percent
    df[COL_ADJUSTED_TAKE_PROFIT] = df[COL_RESISTANCE] * percent

    mask_lt_10 = df[COL_ADJUSTED_STOPLOSS] < 10
    mask_10_100 = (df[COL_ADJUSTED_STOPLOSS] >= 10) & (df[COL_ADJUSTED_STOPLOSS] < 100)
    mask_100_1000 = (df[COL_ADJUSTED_STOPLOSS] >= 100) & (
        df[COL_ADJUSTED_STOPLOSS] < 1000
    )
    maks_gt_1000 = df[COL_ADJUSTED_STOPLOSS] >= 1000

    df.loc[mask_lt_10, COL_ADJUSTED_STOPLOSS] = round(
        df.loc[mask_lt_10, COL_ADJUSTED_STOPLOSS], 2
    )
    df.loc[mask_10_100, COL_ADJUSTED_STOPLOSS] = round(
        df.loc[mask_10_100, COL_ADJUSTED_STOPLOSS], 1
    )
    df.loc[mask_100_1000, COL_ADJUSTED_STOPLOSS] = round(
        df.loc[mask_100_1000, COL_ADJUSTED_STOPLOSS], 0
    )
    df.loc[maks_gt_1000, COL_ADJUSTED_STOPLOSS] = round(
        df.loc[maks_gt_1000, COL_ADJUSTED_STOPLOSS], -1
    )

    mask_lt_10 = df[COL_ADJUSTED_TAKE_PROFIT] < 10
    mask_10_100 = (df[COL_ADJUSTED_TAKE_PROFIT] >= 10) & (
        df[COL_ADJUSTED_TAKE_PROFIT] < 100
    )
    mask_100_1000 = (df[COL_ADJUSTED_TAKE_PROFIT] >= 100) & (
        df[COL_ADJUSTED_TAKE_PROFIT] < 1000
    )
    maks_gt_1000 = df[COL_ADJUSTED_TAKE_PROFIT] >= 1000

    df.loc[mask_lt_10, COL_ADJUSTED_TAKE_PROFIT] = round(
        df.loc[mask_lt_10, COL_ADJUSTED_TAKE_PROFIT], 2
    )
    df.loc[mask_10_100, COL_ADJUSTED_TAKE_PROFIT] = round(
        df.loc[mask_10_100, COL_ADJUSTED_TAKE_PROFIT], 1
    )
    df.loc[mask_100_1000, COL_ADJUSTED_TAKE_PROFIT] = round(
        df.loc[mask_100_1000, COL_ADJUSTED_TAKE_PROFIT], 0
    )
    df.loc[maks_gt_1000, COL_ADJUSTED_TAKE_PROFIT] = round(
        df.loc[maks_gt_1000, COL_ADJUSTED_TAKE_PROFIT], -1
    )

    df[COL_STOPLOSS_PERCENT] = round(
        (df[COL_ADJUSTED_STOPLOSS] - df[COL_BUYING_PRICE]) / df[COL_BUYING_PRICE] * 100,
        2,
    )

    df[COL_TAKE_PROFIT_PERCENT] = round(
        (df[COL_ADJUSTED_TAKE_PROFIT] - df[COL_BUYING_PRICE])
        / df[COL_BUYING_PRICE]
        * 100,
        2,
    )

    df[COL_PROFIT_STOPLOSS_RATE] = abs(
        round(df[COL_TAKE_PROFIT_PERCENT] / df[COL_STOPLOSS_PERCENT], 2)
    )

    return df


def usage():
    print(f"{os.path.basename(__file__)} <stock list.csv>")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()
        exit()

    stock_list_file_name = sys.argv[1]
    if not os.path.exists(stock_list_file_name):
        logging.error(f"{stock_list_file_name} does not exist, please check.")
        exit()

    df = pd.read_csv(stock_list_file_name)
    df = df.rename(columns={"证券代码": COL_STOCK_ID, "证券名称": COL_STOCK_NAME})
    df[COL_STOCK_ID] = df[COL_STOCK_ID].astype(str)
    df = df[~df[COL_STOCK_ID].str.contains("BJ")]
    df = df[~df[COL_STOCK_NAME].str.contains("ST")]
    df[COL_STOCK_ID] = df[COL_STOCK_ID].str.replace("..*", "", regex=True)
    df[COL_STOCK_ID] = df[COL_STOCK_ID].str.zfill(6)

    df.loc[:, COL_BUYING_PRICE] = df[COL_STOCK_ID].swifter.apply(fetch_close_price)

    df[[COL_SUPPORT, COL_RESISTANCE]] = df.swifter.apply(
        calculate_support_resistance,
        args=(start_date_ts, end_date_ts),
        axis=1,
        result_type="expand",
    )

    df = calculate_stoploss_takeprofit(df)

    df = df[
        (df[COL_PROFIT_STOPLOSS_RATE] > 5)
        & (df[COL_TAKE_PROFIT_PERCENT] > 0)
        & (df[COL_STOPLOSS_PERCENT] < -1)
    ]

    df.to_csv(output_file_name, encoding="utf_8_sig", index=False)

    send_email("spot trading report", output_file_name)
