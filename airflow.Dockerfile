FROM apache/airflow:2.9.2-python3.12

# Minimal deps needed by project code imported from DAGs.
# Keep this list small to reduce image size and build time.

USER airflow
RUN pip install --no-cache-dir     akshare     retrying==1.3.4     baostock==0.8.9     pandas_market_calendars==4.6.1     tushare
