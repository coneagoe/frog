FROM apache/airflow:2.9.2-python3.12

USER airflow

RUN pip install --no-cache-dir poetry

COPY poetry.lock pyproject.toml /home/airflow/
RUN cd /home/airflow && poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi --without dev

USER airflow
