"""Application configuration loaded from environment variables.

Central configuration for the Metis server. Values are read from environment
variables (optionally via a ``.env`` file) and validated by pydantic-settings.
"""

from base64 import urlsafe_b64decode
from functools import lru_cache
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlparse

from pydantic import BeforeValidator, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from metis.helpers.pricing import ModelPrice
from metis.helpers.text import strip_to_none


class AppSettings:
    """App-level settings defaults and constants."""

    DEFAULT_APP_ENV = "development"
    DEFAULT_LOG_LEVEL = "INFO"
    DEFAULT_SESSION_COOKIE_NAME = "metis_session"
    DEFAULT_SESSION_TTL_DAYS = 30
    DEFAULT_SESSION_IDLE_DAYS = 7
    VERSION = "0.1.0"
    DEFAULT_FLAGSMITH_API_URL = "https://edge.api.flagsmith.com/api/v1/"


# Flagsmith local evaluation needs a server-side environment key.
SERVER_KEY_PREFIX = "ser."

_GOOGLE_FIELDS = ("google_client_id", "google_client_secret", "google_redirect_uri")
# Plain-string secrets masked by ``Settings.__repr__``; ``SecretStr`` fields mask themselves.
SECRET_FIELDS = frozenset({"encryption_master_key"})


class Settings(BaseSettings):
    """Runtime configuration for the Metis server.

    All configuration is loaded from environment variables, optionally via
    a ``.env`` file. The model is frozen and immutable after creation.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
        # A validation error must never echo the raw inputs (they hold secrets).
        hide_input_in_errors=True,
    )

    # App settings
    app_env: str = Field(
        default=AppSettings.DEFAULT_APP_ENV,
        validation_alias="APP_ENV",
    )
    app_version: str = Field(default=AppSettings.VERSION)
    log_level: str = Field(
        default=AppSettings.DEFAULT_LOG_LEVEL,
        validation_alias="LOG_LEVEL",
    )
    log_json: bool = Field(default=False, validation_alias="LOG_JSON")

    # Infrastructure settings
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    db_pool_size: int = Field(default=10, validation_alias="DB_POOL_SIZE")
    redis_url: str = Field(default="", validation_alias="REDIS_URL")

    # Run lock: held while a worker runs a run, extended by a heartbeat; it must expire
    # soon after a worker dies so crash recovery can pick the run up.
    run_lock_ttl_seconds: int = Field(default=60, ge=3, validation_alias="RUN_LOCK_TTL_SECONDS")
    run_lock_heartbeat_seconds: int = Field(
        default=20, ge=1, validation_alias="RUN_LOCK_HEARTBEAT_SECONDS"
    )
    # Run recovery: a scheduled job re-enqueues runs that lost their lock; a run is retried at
    # most ``run_recovery_max_attempts`` times, and a run with no progress for
    # ``run_stall_seconds`` is failed (it must outlast the longest model call).
    run_recovery_interval_seconds: int = Field(
        default=30, ge=5, le=59, validation_alias="RUN_RECOVERY_INTERVAL_SECONDS"
    )
    run_recovery_max_attempts: int = Field(
        default=3, ge=1, validation_alias="RUN_RECOVERY_MAX_ATTEMPTS"
    )
    run_stall_seconds: int = Field(default=900, ge=300, validation_alias="RUN_STALL_SECONDS")
    # Hard cap on one agent job (Arq's default is 300s, shorter than a research run).
    agent_job_timeout_seconds: int = Field(
        default=1800, ge=60, validation_alias="AGENT_JOB_TIMEOUT_SECONDS"
    )
    # Every specialist a stub (no LLM calls): for the web e2e stack, which has no LLM key.
    agent_stub_specialists: bool = Field(default=False, validation_alias="AGENT_STUB_SPECIALISTS")

    # Security settings
    encryption_master_key: str = Field(default="", validation_alias="ENCRYPTION_MASTER_KEY")
    cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias="CORS_ORIGINS",
    )

    def get_cors_origins(self) -> list[str]:
        """Return CORS origins as a list, parsing from string if needed."""
        if "," in self.cors_origins:
            return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return [self.cors_origins.strip()]

    web_base_url: str = Field(
        default="http://localhost:3000",
        validation_alias="WEB_BASE_URL",
    )

    # Session cookie settings
    session_cookie_name: str = Field(
        default=AppSettings.DEFAULT_SESSION_COOKIE_NAME,
        min_length=1,
        validation_alias="SESSION_COOKIE_NAME",
    )
    session_ttl_days: int = Field(
        default=AppSettings.DEFAULT_SESSION_TTL_DAYS, ge=1, validation_alias="SESSION_TTL_DAYS"
    )
    session_idle_days: int = Field(
        default=AppSettings.DEFAULT_SESSION_IDLE_DAYS, ge=1, validation_alias="SESSION_IDLE_DAYS"
    )
    cookie_domain: Annotated[str | None, BeforeValidator(strip_to_none)] = Field(
        default=None, validation_alias="COOKIE_DOMAIN"
    )
    # Unset: ``Secure`` everywhere except local development (see ``secure_cookies``).
    cookie_secure: Annotated[bool | None, BeforeValidator(strip_to_none)] = Field(
        default=None, validation_alias="COOKIE_SECURE"
    )

    # Google sign-in (OAuth 2.0 + OpenID Connect). Required outside development;
    # in development, leaving them unset means Google is not offered.
    google_client_id: Annotated[str | None, BeforeValidator(strip_to_none)] = Field(
        default=None, validation_alias="GOOGLE_CLIENT_ID"
    )
    google_client_secret: Annotated[SecretStr | None, BeforeValidator(strip_to_none)] = Field(
        default=None, validation_alias="GOOGLE_CLIENT_SECRET"
    )
    google_redirect_uri: Annotated[str | None, BeforeValidator(strip_to_none)] = Field(
        default=None, validation_alias="GOOGLE_REDIRECT_URI"
    )

    # Chat call timeouts: short calls (interview, research, score, advise) and long-output
    # calls (spec, plan), which write a whole document in one answer.
    llm_call_timeout_seconds: float = Field(
        default=60.0, ge=10, validation_alias="LLM_CALL_TIMEOUT_SECONDS"
    )
    llm_long_call_timeout_seconds: float = Field(
        default=240.0, ge=10, validation_alias="LLM_LONG_CALL_TIMEOUT_SECONDS"
    )

    # Most tokens a gate judge call may write (reasoning included). The verdict is one word and
    # a short reason; without a cap a reasoning model writes thousands of tokens per call.
    gate_judge_max_output_tokens: int = Field(
        default=2048, ge=64, validation_alias="GATE_JUDGE_MAX_OUTPUT_TOKENS"
    )

    # Most judge calls a run's gates may make (retries count); past it the judge is skipped
    # and an item that passed its code checks goes through.
    gate_judge_max_calls_per_run: int = Field(
        default=20, ge=0, validation_alias="GATE_JUDGE_MAX_CALLS_PER_RUN"
    )

    # Optional LLM prices, model id -> USD per million tokens (JSON). A model without
    # an entry has no cost recorded; there is no built-in price list.
    llm_prices: dict[str, ModelPrice] = Field(default_factory=dict, validation_alias="LLM_PRICES")
    # Embedding model called with the workspace's LLM key and base_url. It must return
    # 1536-dimension vectors (the competitor KB column); otherwise lookup falls back to names.
    llm_embedding_model: str = Field(
        default="text-embedding-3-small", min_length=1, validation_alias="LLM_EMBEDDING_MODEL"
    )

    # Feature flags: ``static`` reads ``FF_*`` env vars; ``flagsmith`` needs its environment key.
    feature_flag_provider: Literal["static", "flagsmith"] = Field(
        default="static", validation_alias="FEATURE_FLAG_PROVIDER"
    )
    flagsmith_environment_key: Annotated[SecretStr | None, BeforeValidator(strip_to_none)] = Field(
        default=None, validation_alias="FLAGSMITH_ENVIRONMENT_KEY"
    )
    flagsmith_api_url: str = Field(
        default=AppSettings.DEFAULT_FLAGSMITH_API_URL, validation_alias="FLAGSMITH_API_URL"
    )

    # Observability settings (optional)
    sentry_dsn: str | None = Field(default=None, validation_alias="SENTRY_DSN")
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None,
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    langfuse_public_key: str | None = Field(
        default=None,
        validation_alias="LANGFUSE_PUBLIC_KEY",
    )
    langfuse_secret_key: str | None = Field(
        default=None,
        validation_alias="LANGFUSE_SECRET_KEY",
    )
    langfuse_host: str | None = Field(
        default=None,
        validation_alias="LANGFUSE_HOST",
    )

    @model_validator(mode="after")
    def validate_required_fields(self) -> Self:
        """Validate that all required fields were provided."""
        # Check required fields are non-empty
        if not self.database_url:
            raise ValueError("database_url is required")
        if not self.redis_url:
            raise ValueError("redis_url is required")
        if not self.encryption_master_key:
            raise ValueError("encryption_master_key is required")
        if self.llm_long_call_timeout_seconds < self.llm_call_timeout_seconds:
            raise ValueError(
                "llm_long_call_timeout_seconds must not be below llm_call_timeout_seconds"
            )
        if self.run_lock_heartbeat_seconds * 2 >= self.run_lock_ttl_seconds:
            raise ValueError(
                "run_lock_heartbeat_seconds must be under half of run_lock_ttl_seconds"
            )

        return self

    @model_validator(mode="after")
    def validate_feature_flags(self) -> Self:
        """Flagsmith needs its environment key; its API URL must be https."""
        if self.feature_flag_provider == "flagsmith" and self.flagsmith_environment_key is None:
            raise ValueError("flagsmith_environment_key is required when using flagsmith")
        key = self.flagsmith_environment_key
        if (
            self.feature_flag_provider == "flagsmith"
            and key is not None
            and not key.get_secret_value().startswith(SERVER_KEY_PREFIX)
        ):
            raise ValueError(
                f"flagsmith_environment_key must be a server-side key ({SERVER_KEY_PREFIX}…)"
            )
        url = urlparse(self.flagsmith_api_url)
        local_http = url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1")
        if url.scheme != "https" and not (local_http and self.is_development):
            raise ValueError("flagsmith_api_url must be https (http://localhost in development)")
        return self

    @model_validator(mode="after")
    def validate_security_and_environment(self) -> Self:
        """Validate security constraints and environment-specific settings."""
        # Validate encryption master key decodes to 32 bytes
        try:
            decoded = urlsafe_b64decode(self.encryption_master_key)
            if len(decoded) != 32:
                raise ValueError(
                    f"encryption_master_key must decode to 32 bytes, got {len(decoded)}"
                )
        except Exception as e:
            raise ValueError(
                "encryption_master_key must be a valid base64-encoded 32-byte value"
            ) from e

        # Credentialed CORS (session cookie) must never allow any origin.
        if "*" in self.get_cors_origins():
            raise ValueError("cors_origins must list explicit origins, not '*'")

        if not self.is_development:
            for name in _GOOGLE_FIELDS:
                if getattr(self, name) is None:
                    raise ValueError(f"{name} is required outside development")

        if self.session_idle_days > self.session_ttl_days:
            raise ValueError("session_idle_days must not exceed session_ttl_days")

        # In production, force log_json to True
        if self.app_env == "production" and not self.log_json:
            raise ValueError(
                "app_env='production' requires log_json=True. "
                "Set LOG_JSON=true in production environment."
            )

        return self

    @property
    def is_development(self) -> bool:
        """True for local development (``APP_ENV=development``, the default)."""
        return self.app_env == AppSettings.DEFAULT_APP_ENV

    @property
    def google_configured(self) -> bool:
        """Whether Google sign-in has a client id, secret and redirect URI."""
        return all(getattr(self, name) is not None for name in _GOOGLE_FIELDS)

    @property
    def secure_cookies(self) -> bool:
        """Whether the session cookie is ``Secure``: ``COOKIE_SECURE``, else not development."""
        if self.cookie_secure is not None:
            return self.cookie_secure
        return not self.is_development

    def __repr__(self) -> str:
        """Custom repr that redacts secrets."""
        data: dict[str, Any] = {}
        for field_name, _field_info in Settings.model_fields.items():
            value = getattr(self, field_name)
            if field_name in SECRET_FIELDS:
                data[field_name] = "**********"
            else:
                data[field_name] = value
        return f"Settings({data})"


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    This is the only place that reads environment variables. Nothing else
    should access ``os.environ`` directly.
    """
    return Settings()
