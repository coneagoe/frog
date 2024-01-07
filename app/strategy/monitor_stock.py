from datetime import date
import logging
from flask_apscheduler import APScheduler
import pandas as pd
from app import send_email


from stock import (
    is_market_open,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_CURRENT_PRICE,
    COL_MONITOR_PRICE,
    COL_COMMENT,
    get_yesterday_ma,
    fetch_close_price
)
from app.model import db, table_name_monitor_stock


COL_PERIOD = 'period'


@scheduler.task('cron', day_of_week='mon-fri', minute='*/5')
def monitor_stock():
    if not is_market_open():
        return

    with app.app_context():
        with db.engine.connect() as connect:
            df = pd.read_sql(table_name_monitor_stock, con=connect)
            if df.empty:
                return

            df[COL_CURRENT_PRICE] = df[COL_STOCK_ID].apply(fetch_close_price)

            df_tmp = df.copy()

            df_tmp[COL_MONITOR_PRICE] = df_tmp[COL_MONITOR_PRICE].astype(str)
            df0 = df_tmp[df_tmp[COL_MONITOR_PRICE].str.contains('ma')]
            if not df0.empty:
                df0[COL_PERIOD] = \
                    df0[COL_MONITOR_PRICE].str.extract('ma(\d+)').astype(int)

                df0[COL_MONITOR_PRICE] = \
                    df0.apply(lambda row: get_yesterday_ma(row[COL_STOCK_ID], row[COL_PERIOD]), axis=1)

                df_tmp.loc[df0.index, COL_MONITOR_PRICE] = df0[COL_MONITOR_PRICE]

            df_tmp[COL_MONITOR_PRICE] = df_tmp[COL_MONITOR_PRICE].astype(float)

            df_output = df_tmp[(df_tmp[COL_MONITOR_PRICE] >= df_tmp[COL_CURRENT_PRICE])]

            if not df_output.empty:
                fallback_stock_output = f"fallback_stock_{date.today().strftime('%Y%m%d')}.csv"
                df_output = df_output.loc[:, [COL_STOCK_ID, COL_STOCK_NAME,
                                              COL_MONITOR_PRICE, COL_CURRENT_PRICE,
                                              COL_COMMENT]]
                df_output.to_csv(fallback_stock_output, encoding='GBK', index=False)
                logging.info(df_output)
                send_email('fallback stock report', fallback_stock_output)

                df = df[~df[COL_STOCK_ID].isin(df_output[COL_STOCK_ID])]
                df.to_sql(table_name_monitor_stock, con=db.engine, if_exists='replace', index=False)
