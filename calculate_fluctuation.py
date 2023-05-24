from datetime import date
import numpy as np
import pandas as pd
import swifter
from stock import *


conf.config = conf.parse_config()

trading_book_path = get_trading_book_path()
sheet_names = [u"持仓"]
output_book_name = "fluctuation.xlsx"

col_positive_fluctuation = u"正向波动"
col_positive_fluctuation_percent = u"正向波动(%)"
col_negative_fluctuation = u"负向波动"
col_negative_fluctuation_percent = u"负向波动(%)"
col_buy_price = u"买入价"
col_sell_price = u"卖出价"
col_sell_count = u"卖出数量"
col_fluctuation_days = u"波动天数"


def _calculate_fluctuation(df: pd.DataFrame):
    positive_fluctuation = np.nan
    negative_fluctuation = np.nan

    if pd.isna(df[col_fluctuation_days]):
        return positive_fluctuation, negative_fluctuation

    end_date = date.today()
    start_date = end_date - pd.Timedelta(days=df[col_fluctuation_days])
    start_date_ts = start_date.strftime('%Y%m%d')
    end_date_ts = end_date.strftime('%Y%m%d')

    df_history_data = load_history_data(df[col_stock_id], start_date_ts, end_date_ts)
    if df_history_data is not None:
        df_history_data[col_close] = df_history_data[col_close].shift(1)
        positive_fluctuation = \
            df_history_data.apply(lambda x: (x[col_high] - x[col_close]) / x[col_close], axis=1).median()
        positive_fluctuation = round(positive_fluctuation, 4)

        negative_fluctuation = \
            df_history_data.apply(lambda x: (x[col_low] - x[col_close]) / x[col_close], axis=1).median()
        negative_fluctuation = round(negative_fluctuation, 4)

    return positive_fluctuation, negative_fluctuation


def calculate_fluctuation(df: pd.DataFrame):
    df[col_current_price] = df[col_stock_id].swifter.apply(fetch_close_price)
    df[[col_positive_fluctuation, col_negative_fluctuation]] = \
        df.swifter.apply(_calculate_fluctuation, axis=1, result_type='expand')

    df[col_positive_fluctuation_percent] = df[col_positive_fluctuation] * 100
    df[col_negative_fluctuation_percent] = df[col_negative_fluctuation] * 100

    df[col_buy_price] = round(df[col_current_price] * (1 + df[col_negative_fluctuation]), 3)
    df[col_sell_price] = round(df[col_current_price] * (1 + df[col_positive_fluctuation]), 3)

    df[col_buy_count] = np.floor(df[col_buy_amount] * 0.1 / df[col_buy_price] / 100) * 100
    df[col_sell_count] = np.floor(df[col_buy_amount] * 0.1 / df[col_sell_price] / 100) * 100

    df = pd.DataFrame(df, columns=[col_stock_id, col_stock_name,
                                   col_positive_fluctuation_percent,
                                   col_negative_fluctuation_percent,
                                   col_buy_price, col_sell_price,
                                   col_buy_count, col_sell_count])
    return df


for sheet_name in sheet_names:
    df = pd.read_excel(trading_book_path, sheet_name=sheet_name, dtype={col_stock_id: str})
    df = calculate_fluctuation(df)
    df.to_csv(f"fluctuation_{sheet_name}.csv", encoding="utf_8_sig", index=False)
