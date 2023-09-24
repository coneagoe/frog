import base64
import io
import sqlite3
import flask
import pandas as pd

from stock import col_stock_id, col_stock_name, col_current_price, \
    col_monitor_price, col_email, col_comment, col_mobile, col_pc, \
    database_name, monitor_stock_table_name


app = flask.Flask(__name__)


# curl -X POST -F file=@<stock_cvs_path> 'http://localhost:5000/upload_stocks'
@app.route("/upload_stocks", methods=["POST"])
def upload_stocks():
    if flask.request.method == "POST":
        if flask.request.files.get("file"):
            stocks_base64 = flask.request.files["file"].stream.read()
            stocks_str = base64.b64decode(stocks_base64)
            df = pd.read_csv(io.BytesIO(stocks_str), encoding='GBK')
            if all(col in df.columns for col in [col_stock_id, col_stock_name,
                                                 col_monitor_price, col_current_price,
                                                 col_email, col_mobile, col_pc, col_comment]):
                df[col_stock_id] = df[col_stock_id].astype(str)
                df[col_stock_id] = df[col_stock_id].str.zfill(6)

                conn = sqlite3.connect(database_name)
                df.to_sql(monitor_stock_table_name, conn, if_exists='replace', index=False)
                conn.close()
                return "Success"
            else:
                return "Please check csv!"
        else:
            return "No csv!"


if __name__ == "__main__":
    app.run()
