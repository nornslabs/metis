# PRD: chore-core-config

Linear: SHIP-259 · https://linear.app/heimdallabs/issue/SHIP-259/031-global-config-pydantic-settings-that-loads-env

## Problem / Goal

One typed, validated config object for the whole server, loaded once from `.env` and the environment.

## User Stories

1. As a developer, I want global config loaded from `.env` and environment variables, so that I can configure the server without code changes.
2. As a developer, I want all configuration in one typed object, so that I don't need to pass config values throughout the codebase.
3. As a developer, I want validation errors to list all bad variables at startup, so I can fix configuration issues quickly.
4. As a developer, I want `.env.example` to serve as documentation for all required configuration, so I can set up the environment correctly.
5. As a developer, I want test overrides for settings, so that I can run tests without a real environment.
6. As a developer, I want secrets to be redacted in logs and repr, so that sensitive values are never accidentally exposed.

## Requirements

1. `server/metis/core/config.py`: Create `Settings(BaseSettings)` with proper configuration:
   - `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False, frozen=True)`
   - Fields grouped as in LLD:
     - App: `app_env`, `app_version`, `log_level`, `log_json`
     - Infra: `database_url: PostgresDsn`, `db_pool_size`, `redis_url: RedisDsn`
     - Security: `auth_jwt_secret: SecretStr`, `auth_jwt_audience`, `encryption_master_key: SecretStr`, `cors_origins`, `public_base_url`
     - Observability (all optional): `sentry_dsn`, `otel_exporter_otlp_endpoint`, `langfuse_public_key`, `langfuse_secret_key`, `langfuse_host`
2. Add `model_validator(mode="after")`: master key decodes to 32 bytes; `production` forces `log_json=True`.
3. `get_settings()` wrapped in `@lru_cache`. It is the only place that reads env; nothing else uses `os.environ`.
4. `.env.example` at the repo root with every key and a safe placeholder.
5. Add `pydantic-settings` to `server/pyproject.toml` (already present).
6. Tests verify `.env.example` keys match Settings fields and that validation works correctly.

## Out of Scope

- Database migrations
- Table schemas
- Auth implementation
- Sentry and OpenTelemetry wiring (telemetry.py, later)
- Other services

## Touches

- `server/metis/core/config.py` (create/replace)
- `server/pyproject.toml` (already has pydantic-settings)
- `.env.example` (create at repo root)
- `server/tests/core/` (new test directory for config tests)
- `server/metis/entrypoints/api.py` (may reference settings)

## Dependencies

Blocked by: 02 · Scaffold monorepo and tooling. (SHIP-204, done)

## Acceptance Criteria

- [ ] A missing or malformed required var raises one `ValidationError` listing every bad var, and the process exits non-zero.
- [ ] Real env vars override `.env` values (testable).
- [ ] Secrets print as `**********` in `repr(settings)`.
- [ ] A test asserts `.env.example` keys equal the `Settings` fields.
- [ ] Tests can override settings with `app.dependency_overrides[get_settings]` or `get_settings.cache_clear()`.
- [ ] `ruff check`, `mypy --strict`, `pytest` all pass.
- [ ] Master key validation decodes to 32 bytes.
- [ ] Production environment forces `log_json=True`.

## Status

draft