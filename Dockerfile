# --- 1. Builder Stage ---
FROM python:3.12-bookworm AS builder
WORKDIR /app

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_CREATE=true 
    
RUN apt-get update && apt-get install -y git
RUN pip install poetry

COPY pyproject.toml poetry.lock* ./
RUN poetry install --only main --no-root


# --- 2. Development Stage (Local Dev) ---
FROM python:3.12-bookworm AS development
WORKDIR /app

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN apt-get update && apt-get install -y git
RUN pip install poetry

COPY pyproject.toml poetry.lock* ./

# RUN poetry env use /usr/local/bin/python
RUN poetry lock && poetry install --no-root

# COPY . . #Done by vscode

CMD ["sleep", "infinity"]

# --- 3. Production Stage ---
FROM python:3.12-slim-bookworm AS production
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src ./src

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "src/main.py"]


# --- 4. CI Stage (Testing) ---
FROM production AS ci-test
RUN pip install pytest pytest-mock
COPY test/ ./test/
CMD ["pytest"]