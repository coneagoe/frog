# -*- coding: utf-8 -*-
import pandas as pd
from eastmoney import fetch_close_price


execl_name = u"青蛙计划.xlsm"
sheet_name = u"交易计划(1d)"
column_name_count = u"买入数量"
#column_name_profit_loss_ratio = u"盈亏比"
column_name_secid = u"股票代码"
column_name_current_price = u"现价"
column_name_buying_price = u"买入价格"

df = pd.read_excel(execl_name, sheet_name=sheet_name, dtype={column_name_secid: str})
secids = df[column_name_secid]
current_prices = []
for index, value in secids.items():
    current_prices.append(fetch_close_price(value))

series_prices = pd.Series(current_prices, name=column_name_current_price)
df.update(series_prices)

filter = df[column_name_count].isna()
df.loc[filter, column_name_buying_price] = df.loc[filter, column_name_current_price]

df.to_excel("tmp.xlsx", sheet_name=sheet_name)
#print(df)
#print(df[df[column_name_profit_loss_ratio].notna()][column_name_secid])
