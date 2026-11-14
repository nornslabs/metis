"""Application configuration loaded from environment variables.

Central configuration for the Metis server. Values are read from environment
variables (optionally via a ``.env`` file) and validated by pydantic-settings.
"""

from base64 import urlsafe_b64decode
from functools import lru_cache
from typing import Any, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings:
    """App-level settings defaults and constants."""

    DEFAULT_APP_ENV = "development"
    DEFAULT_LOG_LEVEL = "INFO"
    VERSION = "0.1.0"


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
    auth_jwt_secret: str = Field(default="", validation_alias="AUTH_JWT_SECRET")
    auth_jwt_audience: str = Field(default="", validation_alias="AUTH_JWT_AUDIENCE")
    encryption_master_key: str = Field(
        default="", validation_alias="ENCRYPTION_MASTER_KEY"
    )
    cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias="CORS_ORIGINS",
    )

    def get_cors_origins(self) -> list[str]:
        """Return CORS origins as a list, parsing from string if needed."""
        if "," in self.cors_origins:
            return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return [self.cors_origins.strip()]

    public_base_url: str = Field(
        default="http://localhost:3000",
        validation_alias="PUBLIC_BASE_URL",
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
        if not self.auth_jwt_secret:
            raise ValueError("auth_jwt_secret is required")
        if not self.auth_jwt_audience:
            raise ValueError("auth_jwt_audience is required")
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

    def __repr__(self) -> str:
        """Custom repr that redacts secrets."""
        data: dict[str, Any] = {}
        for field_name, _field_info in Settings.model_fields.items():
            value = getattr(self, field_name)
            if field_name in ("auth_jwt_secret", "encryption_master_key"):
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