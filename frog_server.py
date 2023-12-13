import base64
from datetime import date
import io
import os
from flask import Flask, request
from flask_apscheduler import APScheduler
from flask_mail import Mail, Message
import pandas as pd

import conf
from stock import col_stock_id, col_stock_name, col_current_price, \
    col_monitor_price, col_comment, database_name, \
    monitor_stock_table_name, fetch_close_price, get_yesterday_ma, \
    is_market_open
from db import db
from strategy import MonitorStock


col_period = 'period'
encoding = 'GBK'


conf.parse_config()


class Config(object):
    SCHEDULER_API_ENABLED = True


app = Flask(__name__)

# scheduler
app.config.from_object(Config())
scheduler = APScheduler()
scheduler.init_app(app)

# database
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{database_name}"

db.init_app(app)

with app.app_context():
    db.create_all()

# email
app.config['MAIL_SERVER'] = os.environ['MAIL_SERVER']
app.config['MAIL_PORT'] = os.environ['MAIL_PORT']
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_DEFAULT_SENDER'] = os.environ['MAIL_SENDER']
app.config['MAIL_USERNAME'] = os.environ['MAIL_USERNAME']
app.config['MAIL_PASSWORD'] = os.environ['MAIL_PASSWORD']
mail = Mail(app)


# curl -X POST -F file=@<stock_cvs_path> 'http://localhost:5000/upload_stocks'
@app.route("/upload_stocks", methods=["POST"])
def upload_stocks():
    if request.method == "POST":
        if request.files.get("file"):
            stocks_base64 = request.files["file"].stream.read()
            stocks_str = base64.b64decode(stocks_base64)
            df = pd.read_csv(io.BytesIO(stocks_str), encoding=encoding)
            if all(col in df.columns for col in [col_stock_id, col_stock_name,
                                                 col_monitor_price, col_comment]):
                df[col_stock_id] = df[col_stock_id].astype(str)
                df[col_stock_id] = df[col_stock_id].str.zfill(6)
                df = df[[col_stock_id, col_stock_name, col_monitor_price, col_comment]]

                df.to_sql(monitor_stock_table_name, con=db.engine, if_exists='replace', index=False)
                return "Success"
            else:
                return "Please check stocks csv!"
        else:
            return "No stocks csv!"


@app.route("/download_stocks", methods=["GET"])
def download_stocks():
    if request.method == "GET":
        df = pd.read_sql(monitor_stock_table_name, con=db.engine)
        df = df[[col_stock_id, col_stock_name, col_monitor_price, col_comment]]
        stocks_base64 = base64.b64encode(df.to_csv(index=False).encode(encoding))
        return stocks_base64
    else:
        return "Wrong method!"


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
                monitor_stock_output = f"monitor_stock_{date.today().strftime('%Y%m%d')}.csv"
                df_output = df_output.loc[:, [col_stock_id, col_stock_name,
                                              col_monitor_price, col_current_price,
                                              col_comment]]
                df_output.to_csv(monitor_stock_output, encoding=encoding, index=False)
                with app.open_resource(monitor_stock_output) as f:
                    msg = Message('monitor stock report', recipients=[os.environ['MAIL_RECEIVER']])
                    msg.body = "monitor stock report"
                    msg.attach(monitor_stock_output, 'text/csv', f.read())
                    mail.send(msg)

                df = df[~df[col_stock_id].isin(df_output[col_stock_id])]
                df.to_sql(monitor_stock_table_name, con=db.engine, if_exists='replace', index=False)


if __name__ == "__main__":
    scheduler.start()
    app.run()
