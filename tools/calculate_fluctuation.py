import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import swifter  # noqa: F401

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf  # noqa: E402
from stock import (  # noqa: E402
    COL_BUY_AMOUNT,
    COL_BUY_COUNT,
    COL_CLOSE,
    COL_CURRENT_PRICE,
    COL_HIGH,
    COL_LOW,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    fetch_close_price,
    get_trading_book_path,
    load_history_data,
)

conf.parse_config()

trading_book_path = get_trading_book_path()
sheet_names = ["持仓"]
output_book_name = "fluctuation.xlsx"

col_positive_fluctuation = "正向波动"
col_positive_fluctuation_percent = "正向波动(%)"
col_negative_fluctuation = "负向波动"
col_negative_fluctuation_percent = "负向波动(%)"
col_buy_price = "买入价"
col_sell_price = "卖出价"
col_buy_price_reverse = "买入价(反向)"
col_sell_price_reverse = "卖出价(反向)"
col_sell_count = "卖出数量"
col_buy_count_reverse = "买入数量(反向)"
col_sell_count_reverse = "卖出数量(反向)"
col_fluctuation_days = "波动天数"


def _calculate_fluctuation(df: pd.DataFrame):
    positive_fluctuation = np.nan
    negative_fluctuation = np.nan

    if pd.isna(df[col_fluctuation_days]):
        return positive_fluctuation, negative_fluctuation

    end_date = date.today()
    start_date = end_date - pd.Timedelta(days=df[col_fluctuation_days])
    start_date_ts = start_date.strftime("%Y%m%d")
    end_date_ts = end_date.strftime("%Y%m%d")

    df_history_data = load_history_data(
        security_id=df[COL_STOCK_ID],
        period="daily",
        start_date=start_date_ts,
        end_date=end_date_ts,
    )
    if df_history_data is not None:
        df_history_data[COL_CLOSE] = df_history_data[COL_CLOSE].shift(1)
        positive_fluctuation = df_history_data.apply(
            lambda x: (x[COL_HIGH] - x[COL_CLOSE]) / x[COL_CLOSE], axis=1
        ).median()
        positive_fluctuation = round(positive_fluctuation, 4)

        negative_fluctuation = df_history_data.apply(
            lambda x: (x[COL_LOW] - x[COL_CLOSE]) / x[COL_CLOSE], axis=1
        ).median()
        negative_fluctuation = round(negative_fluctuation, 4)

    return positive_fluctuation, negative_fluctuation


def calculate_fluctuation(df: pd.DataFrame):
    df[COL_CURRENT_PRICE] = df[COL_STOCK_ID].swifter.apply(fetch_close_price)
    df[[col_positive_fluctuation, col_negative_fluctuation]] = df.swifter.apply(
        _calculate_fluctuation, axis=1, result_type="expand"
    )

    df[col_positive_fluctuation_percent] = df[col_positive_fluctuation] * 100
    df[col_negative_fluctuation_percent] = df[col_negative_fluctuation] * 100

    df[col_buy_price] = round(
        df[COL_CURRENT_PRICE] * (1 + df[col_negative_fluctuation]), 3
    )
    df[col_sell_price] = round(
        df[COL_CURRENT_PRICE] * (1 + df[col_positive_fluctuation]), 3
    )

    df[COL_BUY_COUNT] = (
        np.floor(df[COL_BUY_AMOUNT] * 0.1 / df[col_buy_price] / 100) * 100
    )
    df[col_sell_count] = (
        np.floor(df[COL_BUY_AMOUNT] * 0.1 / df[col_sell_price] / 100) * 100
    )

    df[col_buy_price_reverse] = round(
        df[COL_CURRENT_PRICE] * (1 - df[col_positive_fluctuation]), 3
    )
    df[col_sell_price_reverse] = round(
        df[COL_CURRENT_PRICE] * (1 - df[col_negative_fluctuation]), 3
    )

    df[col_buy_count_reverse] = (
        np.floor(df[COL_BUY_AMOUNT] * 0.1 / df[col_buy_price_reverse] / 100) * 100
    )
    df[col_sell_count_reverse] = (
        np.floor(df[COL_BUY_AMOUNT] * 0.1 / df[col_sell_price_reverse] / 100) * 100
    )

    df = pd.DataFrame(
        df,
        columns=[
            COL_STOCK_ID,
            COL_STOCK_NAME,
            col_positive_fluctuation_percent,
            col_negative_fluctuation_percent,
            col_buy_price,
            COL_BUY_COUNT,
            col_sell_price,
            col_sell_count,
            col_buy_price_reverse,
            col_buy_count_reverse,
            col_sell_price_reverse,
            col_sell_count_reverse,
        ],
    )
    return df


for sheet_name in sheet_names:
    df = pd.read_excel(
        trading_book_path, sheet_name=sheet_name, dtype={COL_STOCK_ID: str}
    )
    df = calculate_fluctuation(df)
    df.to_csv(f"fluctuation_{sheet_name}.csv", encoding="utf_8_sig", index=False)
