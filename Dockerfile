FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TUSHARE_TOKEN=${TUSHARE_TOKEN}

RUN pip install poetry

# 5. Set the working directory in the container
WORKDIR /app

# 6. Copy the dependency files and install dependencies
COPY poetry.lock pyproject.toml ./
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

# 7. Copy the rest of the application code
COPY . .

# 8. Command to run the application
CMD ["bash", "start_celery.sh"]
