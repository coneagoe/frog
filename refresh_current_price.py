# -*- coding: utf-8 -*-
import pandas as pd
from eastmoney import fetch_close_price

execl_name = u"青蛙计划.xlsm"
sheet_name = u"交易计划(1d)"
column_name_count = u"买入数量"
column_name_profit_loss_ratio = u"盈亏比"
column_name_secid = u"股票代码"

df = pd.read_excel(execl_name, sheet_name=sheet_name, dtype={column_name_secid: str})
secids = df[column_name_secid]
current_prices = []
for index, value in secids.items():
    current_prices.append(fetch_close_price(value))

#print(type(df[column_name_count].notna()))

series_prices = pd.Series(current_prices, name=u"买入价格")
filter_list = df[column_name_count].notna()
df.update(series_prices)
#df.update(series_prices, filter_func=filter_list)
df.to_excel("tmp.xlsx", sheet_name=sheet_name)
#print(df)
#print(df[df[column_name_profit_loss_ratio].notna()][column_name_secid])