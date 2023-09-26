import base64
import io
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import pandas as pd
from stock import col_stock_id, col_stock_name, col_current_price, \
    col_monitor_price, col_email, col_comment, col_mobile, col_pc, \
    database_name, monitor_stock_table_name


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


if __name__ == "__main__":
    app.run()
