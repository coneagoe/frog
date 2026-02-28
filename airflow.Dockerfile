FROM apache/airflow:2.9.2-python3.12

USER airflow

RUN pip install --no-cache-dir \
      akshare \
      retrying \
      baostock \
      pandas_market_calendars \
      tushare
