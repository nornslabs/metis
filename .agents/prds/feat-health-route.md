# PRD: feat-health-route

Linear: SHIP-207 · https://linear.app/heimdallabs/issue/SHIP-207/health-check-route-with-db-and-redis-connectivity

## Problem / Goal

The API needs a `/v1/health` endpoint that verifies the application is healthy and all dependencies (PostgreSQL, Redis) are reachable. This is essential for:
- Container orchestration (Kubernetes/docker health checks)
- Load balancer health probes
- Monitoring and alerting systems
- Developer confidence that the service is running correctly

Currently, the API only has a root `/` endpoint that returns a static response. There's no way to programmatically verify that the service is connected to its required resources.

## User Stories

1. As a DevOps engineer, I want a `GET /v1/health` endpoint that verifies DB connectivity, so that load balancers can route traffic only to healthy instances.

2. As a DevOps engineer, I want the health endpoint to check Redis connectivity, so that the full stack health status is available.

3. As a developer, I want `200 OK` with dependency status on success, so that I can monitor which components are healthy.

4. As a developer, I want the health endpoint to be fast and non-blocking (with reasonable timeout), so that it doesn't slow down normal request flows.

5. As an SRE, I want the health endpoint to fail fast with an error status when dependencies are unavailable, so that unhealthy instances are automatically removed from service.

6. As a developer, I want the health check to use the existing connection pools, so that it doesn't create new connections or leak resources.

7. As a developer, I want the response format to be consistent with our API conventions, so that it's predictable and easy to parse.

## Requirements

1. Add `GET /v1/health` route at `server/metis/modules/ideas/api.py`:
   - Returns `200 OK` with JSON body when healthy
   - Returns `503 Service Unavailable` when dependencies are down
   - Response body: `{"status": "healthy", "timestamp": "<ISO-8601>", "checks": {"database": "ok"|"failed", "redis": "ok"|"failed"}}`

2. Database health check in `server/metis/modules/ideas/service.py`:
   - Use `get_settings().database_url` to get connection string
   - Execute a simple `SELECT 1` query to verify connectivity
   - Use asyncpg connection pool for efficiency
   - Timeout after 2 seconds to prevent blocking

3. Redis health check in `server/metis/modules/ideas/service.py`:
   - Use `get_settings().redis_url` to get connection
   - Ping Redis to verify connectivity
   - Timeout after 2 seconds

4. Health service function `check_health()` that:
   - Takes `workspace_id` as optional parameter (for future multi-tenant health reporting)
   - Returns `HealthStatus` Pydantic model
   - Is idempotent and safe to call frequently

5. Add `HealthStatus` schema in `server/metis/modules/ideas/schemas.py`:
   - `status: Literal["healthy", "unhealthy"]`
   - `timestamp: datetime`
   - `checks: dict[str, Literal["ok", "failed"]]`
   - `errors: list[str] | None` (optional, for debugging)

6. Error handling:
   - Catch connection errors, timeouts, and database errors
   - Return `503 Service Unavailable` on any failure
   - Log at INFO level on failure (not error - health checks are expected to run)

7. Tests in `server/tests/modules/test_health.py`:
   - Unit test with fake database (in-memory SQLite or mock)
   - Integration test with real PostgreSQL and Redis containers
   - Test that `GET /v1/health` returns correct status codes

## Out of Scope

- Authentication/authorization on the health endpoint
- Detailed dependency metrics (latency, pool sizes)
- Self-healing capabilities (restarting failed connections)
- Health check configuration (intervals, thresholds)
- Support for additional dependencies

## Touches

- `server/metis/modules/ideas/api.py` (add health route)
- `server/metis/modules/ideas/service.py` (add health check functions)
- `server/metis/modules/ideas/schemas.py` (add HealthStatus model)
- `server/metis/modules/ideas/repo.py` (may need DB check helper)
- `server/tests/modules/` (new test file)
- `web/` (OpenAPI schema will auto-generate the endpoint)

## Dependencies

- chore-core-errors (SHIP-261, done) - Need error handling patterns
- chore-core-config (SHIP-259, done) - Settings are available

## Testing Decisions

- Unit tests with mocked/async fixtures for DB connection
- Integration tests using the existing `pytest-asyncio` pattern
- Test that the endpoint uses the standard error response format (application/problem+json)
- Follow the existing test patterns in `test_errors.py` for structure and naming

## Acceptance Criteria

- [ ] `GET /v1/health` returns `200 {"status": "healthy", "checks": {"database": "ok", "redis": "ok"}}` when both dependencies are healthy
- [ ] `GET /v1/health` returns `503 {"status": "unhealthy", "checks": {"database": "ok", "redis": "failed"}, "errors": [...]}` when Redis is down but DB is up
- [ ] `GET /v1/health` returns `503` when database is unreachable
- [ ] Health check times out and fails gracefully (under 5 seconds total)
- [ ] Response includes ISO-8601 timestamp
- [ ] Route follows `/v1` prefix convention
- [ ] OpenAPI schema is generated correctly
- [ ] `ruff check`, `mypy --strict`, `pytest` all pass
- [ ] Integration tests pass with docker compose stack

## Status

in progress