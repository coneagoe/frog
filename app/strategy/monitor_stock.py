import base64
import io
import logging

import pandas as pd
from flask import Blueprint, request

from app.model import TABLE_NAME_MONITOR_STOCK, db
from stock import (
    COL_COMMENT,
    COL_CURRENT_PRICE,
    COL_MONITOR_PRICE,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    fetch_close_price,
    get_yesterday_ma,
    is_testing,
)
from utility import send_email

from . import scheduler

COL_PERIOD = "period"
encoding = "GBK"


bp_monitor_stock = Blueprint("monitor_stock", __name__, url_prefix="/monitor_stock")


# @scheduler.task('cron', day_of_week='mon-fri', minute='*/5')
def monitor_stock():
    with scheduler.app.app_context():
        with db.engine.connect() as connect:
            df = pd.read_sql(TABLE_NAME_MONITOR_STOCK, con=connect)
            if df.empty:
                return

            df[COL_CURRENT_PRICE] = df[COL_STOCK_ID].apply(fetch_close_price)

            df_tmp = df.copy()

            df_tmp[COL_MONITOR_PRICE] = df_tmp[COL_MONITOR_PRICE].astype(str)
            df0 = df_tmp[df_tmp[COL_MONITOR_PRICE].str.contains("ma|MA")]
            if not df0.empty:
                df0[COL_PERIOD] = (
                    df0[COL_MONITOR_PRICE].str.extract(r"ma|MA(\d+)").astype(int)
                )  # noqa: W605

                df0[COL_MONITOR_PRICE] = df0.apply(
                    lambda row: get_yesterday_ma(row[COL_STOCK_ID], row[COL_PERIOD]),
                    axis=1,
                )

                df_tmp.loc[df0.index, COL_MONITOR_PRICE] = df0[COL_MONITOR_PRICE]

            df_tmp[COL_MONITOR_PRICE] = df_tmp[COL_MONITOR_PRICE].astype(float)

            df_output = df_tmp[(df_tmp[COL_MONITOR_PRICE] >= df_tmp[COL_CURRENT_PRICE])]

            if not df_output.empty:
                df_output = df_output.loc[
                    :,
                    [
                        COL_STOCK_ID,
                        COL_STOCK_NAME,
                        COL_MONITOR_PRICE,
                        COL_CURRENT_PRICE,
                        COL_COMMENT,
                    ],
                ]
                output = io.StringIO()
                df_output.to_csv(output, index=False, encoding=encoding)
                logging.info(df_output)
                send_email(
                    subject="monitor stock report",
                    template="monitor_stock_report.html",
                    dataframe=df_output.to_html(index=False),
                )

                df = df[~df[COL_STOCK_ID].isin(df_output[COL_STOCK_ID])]
                df.to_sql(
                    TABLE_NAME_MONITOR_STOCK,
                    con=db.engine,
                    if_exists="replace",
                    index=False,
                )


def add_job_monitor_stock():
    if is_testing():
        scheduler.add_job(
            func=monitor_stock, trigger="interval", id="test_monitor_stock", seconds=5
        )
    else:
        scheduler.add_job(
            func=monitor_stock,
            trigger="cron",
            id="monitor_stock",
            day_of_week="mon-fri",
            minute="*/5",
        )


# curl -X POST -F file=@<stock_cvs_path> 'http://localhost:5000/monitor_stock/upload'
@bp_monitor_stock.route("/upload", methods=["POST"])
def upload():
    if request.method == "POST":
        if request.files.get("file"):
            stocks_base64 = request.files["file"].stream.read()
            stocks_str = base64.b64decode(stocks_base64)
            df = pd.read_csv(io.BytesIO(stocks_str), encoding=encoding)
            if all(
                col in df.columns
                for col in [
                    COL_STOCK_ID,
                    COL_STOCK_NAME,
                    COL_MONITOR_PRICE,
                    COL_COMMENT,
                ]
            ):
                df[COL_STOCK_ID] = df[COL_STOCK_ID].astype(str)
                df[COL_STOCK_ID] = df[COL_STOCK_ID].str.zfill(6)
                df = df[[COL_STOCK_ID, COL_STOCK_NAME, COL_MONITOR_PRICE, COL_COMMENT]]

                df.to_sql(
                    TABLE_NAME_MONITOR_STOCK,
                    con=db.engine,
                    if_exists="replace",
                    index=False,
                )
                return "Success"
            else:
                return "Please check stocks csv!"
        else:
            return "No stocks csv!"


@bp_monitor_stock.route("/download", methods=["GET"])
def download():
    if request.method == "GET":
        df = pd.read_sql(TABLE_NAME_MONITOR_STOCK, con=db.engine)
        df = df[[COL_STOCK_ID, COL_STOCK_NAME, COL_MONITOR_PRICE, COL_COMMENT]]
        stocks_base64 = base64.b64encode(df.to_csv(index=False).encode(encoding))
        return stocks_base64
    else:
        return "Wrong method!"
