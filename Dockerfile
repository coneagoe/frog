# 1. Use the official Python image as a parent image
FROM python:3.12-slim

# 2. Build arguments for environment variables
ARG TUSHARE_TOKEN

# 3. Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TUSHARE_TOKEN=${TUSHARE_TOKEN}

# 4. Install Poetry
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
