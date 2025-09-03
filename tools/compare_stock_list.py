import logging
import os
import sys

import pandas as pd

from stock import COL_STOCK_ID

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <stock_list_0> <stock_list_1>")
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

    df2 = df0[~df0[COL_STOCK_ID].isin(df1[COL_STOCK_ID])]
    df3 = df1[~df1[COL_STOCK_ID].isin(df0[COL_STOCK_ID])]

    print(f"stocks in only in {stock_list_0}:")
    print(f"{df2}\n")
    print(f"stocks in only in {stock_list_1}:")
    print(df3)
