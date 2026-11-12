# ============================================
# Stage 1: install Python dependencies
# ============================================
FROM python:3.12-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

# ============================================
# Stage 2: production runner
# ============================================
FROM base AS runner

WORKDIR /app

COPY --from=base /app/.venv /app/.venv
COPY metis/ ./metis/
COPY prompts/ ./prompts/
COPY alembic.ini ./alembic.ini
COPY migrations/ ./migrations/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

RUN useradd --create-home --shell /bin/bash metis && chown -R metis:metis /app
USER metis

EXPOSE 8000
