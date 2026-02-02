# --- 1. Builder Stage ---
FROM python:3.12-bookworm AS builder
WORKDIR /app

# Install poetry
RUN pip install poetry

COPY pyproject.toml poetry.lock* ./

# Install production dependencies only
# (Skipping virtualenv creation to install directly into system)
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi --no-root



# --- 2. Development Stage (Local Dev) ---
FROM builder AS development
# Install development dependencies (e.g., pytest, black)
RUN poetry install --no-interaction --no-root
# Copy all source code for development
COPY . .


# --- 3. Production Stage (Runtime) ---
FROM python:3.12-slim-bookworm AS production
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# Copy source code directory
# (Destination "./src" ensures the directory structure is preserved)
COPY src ./srcs
# Run the application from the src directory
CMD ["python", "src/main.py"]


# --- 4. CI Stage (Testing) ---
# Extend production image for testing
FROM production as ci-test
# Install testing tools directly
RUN pip install pytest pytest-mock
# Copy test files (Not included in production)
COPY test/ ./test/
# (Optional) Set PYTHONPATH if tests cannot find modules in src
ENV PYTHONPATH=/app/src
CMD ["pytest"]