# PRD: chore-core-errors

Linear: SHIP-261 · https://linear.app/heimdallabs/issue/SHIP-261/033-global-error-handler-and-custom-error-codes

## Problem / Goal

Every failure, from any route, returns the same JSON body with a stable custom error code, so the client always knows what happened. Today each failure path is inconsistent; this PRD makes errors uniform, machine-readable, and debuggable.

## User Stories

1. As a developer, I want every API error to return a stable `code` from a fixed catalog, so that the web client can map codes to user-facing messages.
2. As a developer, I want validation failures to include a structured `errors[]` array, so that form errors are easy to surface field-by-field.
3. As a developer, I want unhandled exceptions to return `common.internal_error` with no stack trace or internal detail in the body, so that internals are never leaked to clients.
4. As a developer, I want `Retry-After` headers on retryable errors, so that clients can back off correctly.
5. As a developer, I want 4xx errors logged at INFO and 5xx at WARNING/ERROR, so that log severity matches the actual impact.
6. As a developer, I want `request_id` on every error response matching the access log line, so that tracing a request through logs is trivial.
7. As a developer, I want `ruff` to ban `HTTPException` outside `core/error_handlers.py`, so that error handling stays centralized.
8. As a developer, I want the error code list exported to the web (OpenAPI enum), so that the generated client has full code coverage.

## Requirements

1. `core/errors.py`: Create `ErrorCode(StrEnum)` with every code from the LLD catalog:
   - `common.*`: `internal_error`, `route_not_found`, `method_not_allowed`, `validation_failed`, `rate_limited`, `timeout`, `unavailable`, `conflict`, `bad_request`
   - `auth.*`: `unauthorized`, `forbidden`, `token_expired`, `invalid_credentials`
   - `workspace.*`: `not_found`, `already_exists`, `member_not_found`, `invite_expired`
   - `provider.*`: `not_configured`, `upstream_error`, `budget_exceeded`, `rate_limited`
   - `idea.*`: `not_found`, `invalid_transition`, `not_owner`, `cancelled`
   - `run.*`: `not_found`, `already_running`, `invalid_state`, `timeout`, `cancelled`
   - `research.*`: `no_results`, `upstream_error`, `budget_exceeded`
   - `score.*`: `invalid_rubric`, `upstream_error`, `budget_exceeded`
   - `spec.*`: `not_found`, `conflict`, `invalid_transition`
   - `plan.*`: `not_found`, `conflict`, `invalid_transition`
   - `mcp.*`: `not_connected`, `upstream_error`, `tool_not_found`
   - `export.*`: `not_found`, `conflict`, `upstream_error`, `cancelled`
2. `ErrorSpec(status, title, retryable)` dataclass and `ERROR_CATALOG: dict[ErrorCode, ErrorSpec]` mapping every code to its HTTP status, human title, and retryable flag.
3. `MetisError(code, detail=None, *, errors=None, meta=None)` base exception with `status` from the catalog, plus subclasses:
   - `NotFoundError`, `ConflictError`, `AuthError`, `PermissionDeniedError`, `InvalidInputError`, `UpstreamError`, `BudgetError`, `RateLimitError`
4. `core/error_handlers.py`: `register_error_handlers(app)` registering handlers for:
   - `MetisError` → catalog status, code, detail
   - `RequestValidationError` → `common.validation_failed` with `errors[]`
   - Starlette 404 → `common.route_not_found`
   - Starlette 405 → `common.method_not_allowed`
   - Bare `Exception` → `common.internal_error`, generic detail, stack only in logs
5. Response body: `application/problem+json` with `{type, title, status, code, detail, request_id, retryable, errors?, meta?}`; `Retry-After` header when `meta.retry_after` is set.
6. Log per the LLD handlers table: 4xx at INFO, upstream 5xx at WARNING, unhandled at ERROR with stack.
7. Export the code list to `web` (OpenAPI enum) so the client can map codes to messages.

## Out of Scope

- Database migrations
- Table schemas
- Auth implementation
- Sentry and OpenTelemetry wiring (telemetry.py, later)
- Other services

## Touches

- `server/metis/core/errors.py` (create)
- `server/metis/core/error_handlers.py` (create)
- `server/metis/core/__init__.py` (export new symbols)
- `server/metis/entrypoints/api.py` (call `register_error_handlers(app)` in app factory)
- `server/tests/core/` (new test directory for error handler tests)
- `web/` (OpenAPI enum export of error codes)

## Dependencies

Blocked by: 03.2 · Global logger (needs `request_id` and the logger). (SHIP-260, done)

## Acceptance Criteria

- [x] A test asserts every `ErrorCode` has a catalog entry.
- [x] One test per handler: status, `code`, `request_id` and content type are correct.
- [x] An unhandled exception returns 500 `common.internal_error` with no stack trace or internal message in the body.
- [x] `ruff` bans `HTTPException` outside `core/error_handlers.py`.
- [x] `ruff check`, `mypy --strict`, `pytest` all pass.

## Status

done