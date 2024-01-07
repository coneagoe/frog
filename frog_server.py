from datetime import date
import os
from flask import Flask, request
from flask_mail import Mail, Message
import pandas as pd

import conf
from stock import COL_STOCK_ID, COL_STOCK_NAME, COL_CURRENT_PRICE, \
    COL_MONITOR_PRICE, COL_COMMENT, DATABASE_NAME, \
    monitor_stock_table_name, fetch_close_price, get_yesterday_ma, \
    is_market_open
from app import db, create_app, scheduler, monitor_stock

col_period = 'period'


conf.parse_config()

app = create_app(os.environ['FROG_SERVER_CONFIG'])

with app.app_context():
    db.create_all()


@scheduler.task('cron', day_of_week='mon-fri', minute='*/5')
def monitor_stocks():
    if not is_market_open():
        return

    with app.app_context():
        with db.engine.connect() as connect:
            df = pd.read_sql(monitor_stock_table_name, con=connect)
            if df.empty:
                return

            df[COL_CURRENT_PRICE] = df[COL_STOCK_ID].apply(fetch_close_price)

            df_tmp = df.copy()

            df_tmp[COL_MONITOR_PRICE] = df_tmp[COL_MONITOR_PRICE].astype(str)
            df0 = df_tmp[df_tmp[COL_MONITOR_PRICE].str.contains('ma')]
            if not df0.empty:
                df0[col_period] = \
                    df0[COL_MONITOR_PRICE].str.extract('ma(\d+)').astype(int)

                df0[COL_MONITOR_PRICE] = \
                    df0.apply(lambda row: get_yesterday_ma(row[COL_STOCK_ID], row[col_period]), axis=1)

                df_tmp.loc[df0.index, COL_MONITOR_PRICE] = df0[COL_MONITOR_PRICE]

            df_tmp[COL_MONITOR_PRICE] = df_tmp[COL_MONITOR_PRICE].astype(float)

            df_output = df_tmp[(df_tmp[COL_MONITOR_PRICE] >= df_tmp[COL_CURRENT_PRICE])]

            if not df_output.empty:
                monitor_stock_output = f"monitor_stock_{date.today().strftime('%Y%m%d')}.csv"
                df_output = df_output.loc[:, [COL_STOCK_ID, COL_STOCK_NAME,
                                              COL_MONITOR_PRICE, COL_CURRENT_PRICE,
                                              COL_COMMENT]]
                df_output.to_csv(monitor_stock_output, encoding=encoding, index=False)
                with app.open_resource(monitor_stock_output) as f:
                    msg = Message('monitor stock report', recipients=[os.environ['MAIL_RECEIVER']])
                    msg.body = "monitor stock report"
                    msg.attach(monitor_stock_output, 'text/csv', f.read())
                    mail.send(msg)

                df = df[~df[COL_STOCK_ID].isin(df_output[COL_STOCK_ID])]
                df.to_sql(monitor_stock_table_name, con=db.engine, if_exists='replace', index=False)


if __name__ == "__main__":
    scheduler.start()
    app.run()
