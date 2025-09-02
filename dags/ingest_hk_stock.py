from datetime import datetime, timedelta

import akshare as ak

# import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1),
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "ingest_akshare_hk_stock_daily",
    default_args=default_args,
    schedule_interval="0 1 * * *",  # 每天凌晨 1 点运行
    catchup=False,
)


def ingest_akshare_hk_stock_daily(**kwargs):
    # 获取 港股通 日线数据
    stock_hk_daily_df = ak.stock_hk_daily(symbol="00001", adjust="qfq")
    # 连接数据库
    engine = create_engine("postgresql://quant:quant@db:5432/quant")
    # 写入数据库
    stock_hk_daily_df.to_sql("hk_stock_daily", engine, if_exists="append", index=False)


ingest_task = PythonOperator(
    task_id="ingest_akshare_hk_stock_daily",
    python_callable=ingest_akshare_hk_stock_daily,
    dag=dag,
)
