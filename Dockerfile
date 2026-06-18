FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TUSHARE_TOKEN=${TUSHARE_TOKEN}

RUN apk add --no-cache procps bash gcc g++ musl-dev linux-headers curl git
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:${PATH}"

COPY celery_app.py celery_config.py start_celery.sh config.py config.ini ./
COPY *.csv ./
COPY common ./common
COPY conf ./conf
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
COPY paper_trading ./paper_trading

CMD ["bash", "start_celery.sh"]
