# syntax=docker/dockerfile:1.6

FROM python:3.12-bookworm AS builder-main
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir poetry

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_CREATE=true

COPY pyproject.toml poetry.lock* ./
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    --mount=type=cache,target=/root/.cache/pip \
    poetry install --only main --no-root


FROM python:3.12-bookworm AS builder-dev
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir poetry

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_CREATE=true

COPY pyproject.toml poetry.lock* ./
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    --mount=type=cache,target=/root/.cache/pip \
    poetry install --with dev --no-root


# ---- prod runtime (main only) ----
FROM python:3.12-bookworm AS prod
WORKDIR /app
COPY --from=builder-main /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY src ./src
CMD ["python", "src/main.py"]


# ---- CI test runner (dev venv) ----
FROM python:3.12-bookworm AS test
WORKDIR /app
COPY --from=builder-dev /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY src ./src
COPY tests ./tests
ENV PYTHONPATH=/app/src
CMD ["pytest", "-q"]
