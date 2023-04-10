import sys
import os
from datetime import date
import pandas as pd
import swifter
import conf
from stock import *


pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)

conf.config = conf.parse_config()

percent = 0.995

n = 360
end_date = date.today()
start_date = end_date - pd.Timedelta(days=n)
start_date_ts = start_date.strftime('%Y%m%d')
end_date_ts = end_date.strftime('%Y%m%d')

def calculate_stoploss_takeprofit(df: pd.DataFrame):
    df[col_adjusted_stoploss] = df[col_support] * percent
    df[col_adjusted_take_profit] = df[col_resistance] * percent

    mask_lt_10 = df[col_adjusted_stoploss] < 10
    mask_10_100 = (df[col_adjusted_stoploss] >= 10) & (df[col_adjusted_stoploss] < 100)
    mask_100_1000 = (df[col_adjusted_stoploss] >= 100) & (df[col_adjusted_stoploss] < 1000)
    maks_gt_1000 = df[col_adjusted_stoploss] >= 1000

    df.loc[mask_lt_10, col_adjusted_stoploss] = round(df.loc[mask_lt_10, col_adjusted_stoploss], 2)
    df.loc[mask_10_100, col_adjusted_stoploss] = round(df.loc[mask_10_100, col_adjusted_stoploss], 1)
    df.loc[mask_100_1000, col_adjusted_stoploss] = round(df.loc[mask_100_1000, col_adjusted_stoploss], 0)
    df.loc[maks_gt_1000, col_adjusted_stoploss] = round(df.loc[maks_gt_1000, col_adjusted_stoploss], -1)

    mask_lt_10 = df[col_adjusted_take_profit] < 10
    mask_10_100 = (df[col_adjusted_take_profit] >= 10) & (df[col_adjusted_take_profit] < 100)
    mask_100_1000 = (df[col_adjusted_take_profit] >= 100) & (df[col_adjusted_take_profit] < 1000)
    maks_gt_1000 = df[col_adjusted_take_profit] >= 1000

    df.loc[mask_lt_10, col_adjusted_take_profit] = round(df.loc[mask_lt_10, col_adjusted_take_profit], 2)
    df.loc[mask_10_100, col_adjusted_take_profit] = round(df.loc[mask_10_100, col_adjusted_take_profit], 1)
    df.loc[mask_100_1000, col_adjusted_take_profit] = round(df.loc[mask_100_1000, col_adjusted_take_profit], 0)
    df.loc[maks_gt_1000, col_adjusted_take_profit] = round(df.loc[maks_gt_1000, col_adjusted_take_profit], -1)

    df[col_stoploss_percent] = \
        round((df[col_adjusted_stoploss] - df[col_buying_price]) / df[col_buying_price] * 100, 2)

    df[col_take_profit_percent] = \
        round((df[col_adjusted_take_profit] - df[col_buying_price]) / df[col_buying_price] * 100, 2)

    df[col_profit_stoploss_rate] = abs(round(df[col_take_profit_percent] / df[col_stoploss_percent], 2))

    return df


def usage():
    print(f"{os.path.basename(__file__)} <stock list.csv>")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        usage()
        exit()

    stock_list_file_name = sys.argv[1]
    if not os.path.exists(stock_list_file_name):
        logging.error(f"{stock_list_file_name} does not exist, please check.")
        exit()

    df = pd.read_csv(stock_list_file_name)
    df = df.rename(columns={u'证券代码': col_stock_id, u'证券名称': col_stock_name})
    df = df[~df[col_stock_id].str.contains('BJ')]
    df = df[~df[col_stock_name].str.contains('ST')]
    df[col_stock_id] = df[col_stock_id].str[:-3]

    df.loc[:, col_buying_price] = df[col_stock_id].swifter.apply(fetch_close_price)

    df[[col_support, col_resistance]] = \
        df.swifter.apply(calculate_support_resistance, args=(start_date_ts, end_date_ts),
                         axis=1, result_type='expand')

    df = calculate_stoploss_takeprofit(df)

    df0 = df[(df[col_profit_stoploss_rate] > 5) & (df[col_take_profit_percent] > 0)]

    df0.to_csv('spot_trading.csv', encoding='utf_8_sig', index=False)
