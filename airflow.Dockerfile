FROM apache/airflow:3.3.0-python3.12

USER airflow

RUN pip install --no-cache-dir \
      "apache-airflow==${AIRFLOW_VERSION}" \
      akshare \
      retrying \
      baostock \
      pandas_market_calendars \
      tushare \
      yfinance==0.2.55
