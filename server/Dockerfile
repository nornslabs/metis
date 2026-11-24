FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS runner

# No libpq5 needed; psycopg[binary] bundles it
RUN useradd --create-home --shell /bin/bash metis

WORKDIR /app

COPY --from=builder --chown=metis:metis /app/.venv /app/.venv
COPY --chown=metis:metis metis/ ./metis/
COPY --chown=metis:metis alembic.ini ./alembic.ini
COPY --chown=metis:metis migrations/ ./migrations/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER metis

EXPOSE 8000

# Default process: API server (compose.yaml overrides for worker/scheduler/migrate)
CMD ["uvicorn", "metis.entrypoints.api:app", "--host", "0.0.0.0", "--port", "8000"]