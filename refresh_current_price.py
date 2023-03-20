# -*- coding: utf-8 -*-
import logging
import pandas as pd
import conf
from stock import *


sheet_name = u"交易计划(1d)"
col_buy_count = u"买入数量"
col_buying_price = u"买入价格"
output_book_name = "tmp.xlsx"


conf.config = conf.parse_config()

trading_book_path = get_trading_book_path()


df = pd.read_excel(trading_book_path, sheet_name=sheet_name, dtype={col_stock_id: str})
security_ids = df[col_stock_id]
current_prices = []
for index, value in security_ids.items():
    current_prices.append(fetch_close_price(value))

series_prices = pd.Series(current_prices, name=col_current_price)
df.update(series_prices)

filter_na = df[col_buy_count].isna()
df.loc[filter_na, col_buying_price] = df.loc[filter_na, col_current_price]

df.to_excel(output_book_name, sheet_name=sheet_name)
