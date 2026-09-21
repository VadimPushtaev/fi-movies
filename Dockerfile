FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=2.1.4 \
    POETRY_HOME=/opt/poetry \
    POETRY_VIRTUALENVS_CREATE=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sSL https://install.python-poetry.org | python3 -

ENV PATH="${POETRY_HOME}/bin:${PATH}"

WORKDIR /app
COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN poetry install --only main

CMD ["uvicorn", "fi_movies.web:app", "--host", "0.0.0.0", "--port", "8000"]

