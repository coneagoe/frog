# 1. Use the official Python image as a parent image
FROM python:3.11-slim

# 2. Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Install Poetry
RUN pip install poetry

# 4. Set the working directory in the container
WORKDIR /app

# 5. Copy the dependency files and install dependencies
COPY poetry.lock pyproject.toml ./
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

# 6. Copy the rest of the application code
COPY . .

# 7. Command to run the application
CMD ["bash", "start_celery.sh"]
