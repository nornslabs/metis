# syntax=docker/dockerfile:1

# ============================================
# Stage 1: build the production virtualenv
# ============================================
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ============================================
# Stage 2: minimal runtime image
# ============================================
FROM python:3.12-slim AS runner

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash metis

WORKDIR /app

COPY --from=builder --chown=metis:metis /app/.venv /app/.venv
COPY --chown=metis:metis metis/ ./metis/
COPY --chown=metis:metis prompts/ ./prompts/
COPY --chown=metis:metis alembic.ini ./alembic.ini
COPY --chown=metis:metis migrations/ ./migrations/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER metis

EXPOSE 8000
