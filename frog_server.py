import base64
from datetime import date
import io
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import pandas as pd

import conf
from stock import col_stock_id, col_stock_name, col_current_price, \
    col_monitor_price, col_comment, database_name, \
    monitor_stock_table_name, fetch_close_price, get_yesterday_ma, \
    is_market_open
from utility import send_email


col_period = 'period'


conf.config = conf.parse_config()


class Config(object):
    SCHEDULER_API_ENABLED = True


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class MonitorStock(db.Model):
    __tablename__ = monitor_stock_table_name

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[str] = mapped_column(String(6), name=col_stock_id, nullable=False)
    stock_name: Mapped[str] = mapped_column(String(20), name=col_stock_name, nullable=False)
    monitor_price: Mapped[str] = mapped_column(String(10), name=col_monitor_price, nullable=False)
    comment: Mapped[str] = mapped_column(String)

    def __repr__(self):
        return f"<MonitorStock(stock_id={self.stock_id}, stock_name={self.stock_name}, " \
               f"monitor_price={self.monitor_price}, comment={self.comment})>"


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


# curl -X POST -F file=@<stock_cvs_path> 'http://localhost:5000/upload_stocks'
@app.route("/upload_stocks", methods=["POST"])
def upload_stocks():
    if request.method == "POST":
        if request.files.get("file"):
            stocks_base64 = request.files["file"].stream.read()
            stocks_str = base64.b64decode(stocks_base64)
            df = pd.read_csv(io.BytesIO(stocks_str), encoding='GBK')
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
        stocks_base64 = base64.b64encode(df.to_csv(index=False).encode('GBK'))
        return stocks_base64
    else:
        return "Wrong method!"


@scheduler.task('cron', day_of_week='mon-fri', minute='*/5')
def monitor_stocks():
    if not is_market_open():
        return

    with app.app_context():
        df = pd.read_sql(monitor_stock_table_name, con=db.engine)
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
            # print(df_output)
            send_email('fallback stock report', fallback_stock_output)

            df = df[~df[col_stock_id].isin(df_output[col_stock_id])]
            df.to_sql(monitor_stock_table_name, con=db.engine, if_exists='replace', index=False)


if __name__ == "__main__":
    scheduler.start()
    app.run()
