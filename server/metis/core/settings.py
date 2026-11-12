"""Application settings loaded from environment variables.

Central configuration for the Metis server. Values are read from environment
variables (optionally via a ``.env`` file) and validated by pydantic-settings.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Metis server."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core infra
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    redis_url: str = Field(default="", validation_alias="REDIS_URL")

    # Auth / security
    auth_jwt_secret: str = Field(default="", validation_alias="AUTH_JWT_SECRET")
    auth_jwt_audience: str = Field(default="", validation_alias="AUTH_JWT_AUDIENCE")
    encryption_master_key: str = Field(
        default="", validation_alias="ENCRYPTION_MASTER_KEY"
    )
    cors_origin: str = Field(default="", validation_alias="CORS_ORIGIN")

    # Langfuse observability
    langfuse_public_key: str = Field(default="", validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="", validation_alias="LANGFUSE_HOST")

    # Telemetry / error reporting
    otel_exporter_otlp_endpoint: str = Field(
        default="", validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    sentry_dsn: str = Field(default="", validation_alias="SENTRY_DSN")


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
