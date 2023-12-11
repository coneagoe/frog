import logging
from flask_apscheduler import APScheduler

from stock import is_market_open, monitor_stock_table_name, \
    col_stock_id, col_stock_name, col_current_price, \
    col_monitor_price, col_period, col_comment, get_yesterday_ma


@scheduler.task('cron', day_of_week='mon-fri', minute='*/5')
def monitor_stocks():
    if not is_market_open():
        return

    with app.app_context():
        with db.engine.connect() as connect:
            df = pd.read_sql(monitor_stock_table_name, con=connect)
            if df.empty:
                return

            df[col_current_price] = df[col_stock_id].apply(fetch_close_price)

            df_tmp = df.copy()

            df_tmp[col_monitor_price] = df_tmp[col_monitor_price].astype(str)
            df0 = df_tmp[df_tmp[col_monitor_price].str.contains('ma')]
            if not df0.empty:
                df0[col_period] = \
                    df0[col_monitor_price].str.extract('ma(\d+)').astype(int)

                df0[col_monitor_price] = \
                    df0.apply(lambda row: get_yesterday_ma(row[col_stock_id], row[col_period]), axis=1)

                df_tmp.loc[df0.index, col_monitor_price] = df0[col_monitor_price]

            df_tmp[col_monitor_price] = df_tmp[col_monitor_price].astype(float)

            df_output = df_tmp[(df_tmp[col_monitor_price] >= df_tmp[col_current_price])]

            if not df_output.empty:
                fallback_stock_output = f"fallback_stock_{date.today().strftime('%Y%m%d')}.csv"
                df_output = df_output.loc[:, [col_stock_id, col_stock_name,
                                              col_monitor_price, col_current_price,
                                              col_comment]]
                df_output.to_csv(fallback_stock_output, encoding='GBK', index=False)
                logging.info(df_output)
                send_email('fallback stock report', fallback_stock_output)

                df = df[~df[col_stock_id].isin(df_output[col_stock_id])]
                df.to_sql(monitor_stock_table_name, con=db.engine, if_exists='replace', index=False)
