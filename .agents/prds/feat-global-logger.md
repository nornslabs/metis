# PRD: feat-global-logger

Linear: SHIP-260 · https://linear.app/heimdallabs/issue/SHIP-260/032-global-logger-structlog-with-request-context

## Problem / Goal

One logger setup for api, worker and scheduler: JSON lines in production, readable console locally, with request and run context on every line.

## User Stories

1. As a developer, I want a single `configure_logging(settings)` function, so that all services (api, worker, scheduler) use consistent log formatting.
2. As a developer, I want JSON output in production and console output locally, so that logs are machine-readable in prod but human-readable during development.
3. As a developer, I want `get_logger(name)` helper, so that I can create loggers that automatically include service, env, version context.
4. As a developer, I want `bind_context(**kv)` helper, so that I can attach request_id, run_id, workspace_id to log lines.
5. As a user, I want every log line to include `request_id` when inside a request, so that I can trace a request's entire lifecycle.
6. As a developer, I want all stdlib loggers (uvicorn, sqlalchemy, arq, httpx) routed through structlog, so that third-party logs follow the same format.
7. As a user, I want the `X-Request-ID` header echoed in responses, so that I can correlate client-side requests with server logs.
8. As a security engineer, I want sensitive values under keys matching `key|token|secret|password|authorization` to be masked, so that credentials are never logged.
9. As a developer, I want no `print` statements and no `logging.getLogger()` in app code (enforced by ruff), so that all logging goes through the structured pipeline.

## Requirements

1. `server/metis/core/logging.py`: Create logging module with:
   - `configure_logging(settings: Settings) -> None`: Configures structlog with processors `merge_contextvars`, `add_log_level`, ISO UTC `TimeStamper`, `add_service_info` (service, env, version), `redact_secrets`, `StackInfoRenderer`, `format_exc_info`. Uses `JSONRenderer` when `settings.log_json`, else `ConsoleRenderer`.
   - Route stdlib loggers (uvicorn, sqlalchemy, arq, httpx) through `structlog.stdlib.ConsoleRendererBoundLoggerWrapper`; set levels from `settings.log_level`.
   - `get_logger(name: str) -> structlog.stdlib.BoundLogger`: Returns a logger pre-bound with service info.
   - `bind_context(**kv: Any) -> None`: Binds context variables (request_id, run_id, etc.) to all subsequent log lines in the current context.

2. `server/metis/core/middleware.py`: Create FastAPI middleware:
   - `RequestContextMiddleware`: Reads `X-Request-ID` header or creates a UUIDv7 if not present; binds `request_id` to context; echoes the header in response; clears context at end of request; writes one `http.request` log line at DEBUG level for health checks, INFO level otherwise with `method, path, status, duration_ms`.

3. Update entrypoints to call `configure_logging(get_settings())` at startup:
   - `server/metis/entrypoints/api.py`
   - `server/metis/entrypoints/worker.py` (to be created/updated)
   - `server/metis/entrypoints/scheduler.py`

4. Add `PY001` (no `print`) and `PLC0415` (no `logging.getLogger`) to ruff rules.

## Out of Scope

- Custom formatters for specific log messages
- Log rotation or shipping to external services (handled by OpenTelemetry/logs, later)
- Metrics collection (Prometheus, later)

## Touches

- `server/metis/core/logging.py` (create)
- `server/metis/core/middleware.py` (create)
- `server/metis/entrypoints/api.py` (update)
- `server/metis/entrypoints/worker.py` (update)
- `server/metis/entrypoints/scheduler.py` (update)
- `server/pyproject.toml` (add ruff rules)
- `server/tests/core/test_logging.py` (create)

## Dependencies

Blocked by: chore-core-config (SHIP-259, done)

## Acceptance Criteria

- [x] Every log line is one JSON object with `ts, level, event, logger, service, env, version` and, inside a request, `request_id`.
- [x] Values under keys matching `key|token|secret|password|authorization` are masked (test).
- [x] Two concurrent requests never mix their `request_id` (test with asyncio.gather).
- [x] The response always carries `X-Request-ID`.
- [x] No `print` and no `logging.getLogger` in app code (ruff rule).
- [x] Health check requests are logged at DEBUG level, regular requests at INFO.
- [x] `ruff check`, `mypy --strict`, `pytest` all pass.

## Status

done