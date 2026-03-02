FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TUSHARE_TOKEN=${TUSHARE_TOKEN}

RUN pip install poetry

RUN apk add --no-cache procps

WORKDIR /app

COPY poetry.lock pyproject.toml ./
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

COPY . .

CMD ["bash", "start_celery.sh"]
