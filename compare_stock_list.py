import logging
import os
import sys
import pandas as pd
from stock import col_stock_id


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f'Usage: {sys.argv[0]} <stock_list_0> <stock_list_1>')
        exit(1)

    stock_list_0 = sys.argv[1]
    if not os.path.exists(stock_list_0):
        logging.warning(f"{stock_list_0} does not exist, please check!")
        exit()

    stock_list_1 = sys.argv[2]
    if not os.path.exists(stock_list_1):
        logging.warning(f"{stock_list_1} does not exist, please check!")
        exit()

    df0 = pd.read_excel(stock_list_0)
    df1 = pd.read_excel(stock_list_1)

    df2 = df0[~df0[col_stock_id].isin(df1[col_stock_id])]
    df3 = df1[~df1[col_stock_id].isin(df0[col_stock_id])]

    print(f'stocks in only in {stock_list_0}:')
    print(df2)
    print()
    print(f'stocks in only in {stock_list_1}:')
    print(df3)
