FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TUSHARE_TOKEN=${TUSHARE_TOKEN}

RUN pip install poetry

RUN apk add --no-cache procps bash

WORKDIR /app

COPY poetry.lock pyproject.toml ./
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

COPY celery_app.py celery_config.py start_celery.sh config.py config.ini ./
COPY *.csv ./
COPY common ./common
COPY conf ./conf
COPY backtest ./backtest
COPY download ./download
COPY fund ./fund
COPY indicator ./indicator
COPY monitor ./monitor
COPY ocr ./ocr
COPY stock ./stock
COPY storage ./storage
COPY task ./task
COPY tools ./tools
COPY trigger ./trigger
COPY utility ./utility

CMD ["bash", "start_celery.sh"]
