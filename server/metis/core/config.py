"""Application configuration loaded from environment variables.

Central configuration for the Metis server. Values are read from environment
variables (optionally via a ``.env`` file) and validated by pydantic-settings.
"""

from base64 import urlsafe_b64decode
from functools import lru_cache
from typing import Annotated, Any, Self

from pydantic import BeforeValidator, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from metis.helpers.text import strip_to_none


class AppSettings:
    """App-level settings defaults and constants."""

    DEFAULT_APP_ENV = "development"
    DEFAULT_LOG_LEVEL = "INFO"
    DEFAULT_SESSION_COOKIE_NAME = "metis_session"
    DEFAULT_SESSION_TTL_DAYS = 30
    DEFAULT_SESSION_IDLE_DAYS = 7
    VERSION = "0.1.0"


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
