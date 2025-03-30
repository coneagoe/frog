from datetime import datetime
import logging
import os
import sys
import argparse
import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf
from stock import (
    load_history_data,
    get_last_trading_day,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_OPEN,
    COL_CLOSE,
)


conf.parse_config()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--start", required=True, help="Start date in YYYY-MM-DD format")
    parser.add_argument("-e", "--end", required=False, help="End date in YYYY-MM-DD format")
    parser.add_argument("-l", "--csv", required=True, help="stock.csv")
    args = parser.parse_args()

    if args.end is None:
        args.end = get_last_trading_day() 

    df = pd.read_csv(args.csv, encoding='utf_8_sig', dtype={COL_STOCK_ID: str})

    df[COL_OPEN] = df[COL_STOCK_ID].apply(
        lambda x: load_history_data(security_id=x, period='daily', start_date=args.start,
                                    end_date=args.start)[COL_OPEN].values[0]
    )
    df[COL_CLOSE] = df[COL_STOCK_ID].apply(
        lambda x: load_history_data(security_id=x, period='daily', start_date=args.end,
                                    end_date=args.end)[COL_CLOSE].values[0]
    )

    df[u'涨幅'] = (df[COL_CLOSE] - df[COL_OPEN]) / df[COL_OPEN] * 100
    df[u'涨幅'] = df[u'涨幅'].round(2)
    df = df[df[u'涨幅'] > 1]
    df = df.sort_values(by=u'涨幅', ascending=False)

    df.to_csv('result.csv', encoding='utf_8_sig', index=False)


if __name__ == "__main__":
    main()
