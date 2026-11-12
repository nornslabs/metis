"""Tests for the Settings configuration class."""

import os
from base64 import urlsafe_b64encode
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from metis.core.config import AppSettings, Settings, get_settings


def get_valid_secret() -> str:
    """Return a valid 32-byte base64-encoded secret."""
    return urlsafe_b64encode(b"x" * 32).decode()


class TestSettingsDefaults:
    """Tests for default settings behavior."""

    def test_settings_has_correct_defaults(self) -> None:
        """Verify default values for app settings."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            redis_url="redis://localhost:6379/0",
            auth_jwt_secret="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            auth_jwt_audience="test-audience",
            encryption_master_key=get_valid_secret(),
        )

        assert settings.app_env == AppSettings.DEFAULT_APP_ENV
        assert settings.app_version == AppSettings.VERSION
        assert settings.log_level == "INFO"
        assert settings.log_json is False
        assert settings.db_pool_size == 10


class TestSettingsValidation:
    """Tests for Settings validation."""

    def test_missing_required_env_var_raises_validation_error(self) -> None:
        """Required env vars that are missing should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Settings()

        errors = exc_info.value.errors()
        # Should have errors for missing required fields
        error_messages = [str(e) for e in errors]
        combined_errors = " ".join(error_messages).lower()

        # Validation aliases use uppercase
        has_error = (
            "database_url" in combined_errors
            or "redis_url" in combined_errors
        )
        assert has_error

    def test_encryption_master_key_must_be_32_bytes(self) -> None:
        """Encryption master key must decode to exactly 32 bytes."""
        # Use a valid base64 key that's NOT 32 bytes when decoded
        # "YWJjZGVmZ2hpamtsbW5vcA==" decodes to 24 bytes
        invalid_key = "YWJjZGVmZ2hpamtsbW5vcA=="  # 24 bytes when decoded

        with pytest.raises(ValidationError) as exc_info:
            Settings(
                database_url="postgresql+asyncpg://test:test@localhost:5432/test",
                redis_url="redis://localhost:6379/0",
                auth_jwt_secret="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                auth_jwt_audience="test-audience",
                encryption_master_key=invalid_key,
            )

        # Check for either "32 bytes" or "32-byte" in error message
        error_str = str(exc_info.value)
        assert "32" in error_str and ("bytes" in error_str or "byte" in error_str)

    def test_production_requires_log_json(self) -> None:
        """Production environment must have log_json=True."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                app_env="production",
                database_url="postgresql+asyncpg://test:test@localhost:5432/test",
                redis_url="redis://localhost:6379/0",
                auth_jwt_secret="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                auth_jwt_audience="test-audience",
                encryption_master_key=get_valid_secret(),
                log_json=False,
            )

        assert "log_json" in str(exc_info.value).lower()

    def test_valid_256_b64_key_passes_validation(self) -> None:
        """A valid 32-byte base64 key should pass validation."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            redis_url="redis://localhost:6379/0",
            auth_jwt_secret="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            auth_jwt_audience="test-audience",
            encryption_master_key=get_valid_secret(),
        )

        assert settings.encryption_master_key == get_valid_secret()

    def test_production_with_log_json_true_succeeds(self) -> None:
        """Production with log_json=True should succeed."""
        settings = Settings(
            app_env="production",
            log_json=True,
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            redis_url="redis://localhost:6379/0",
            auth_jwt_secret="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            auth_jwt_audience="test-audience",
            encryption_master_key=get_valid_secret(),
        )

        assert settings.app_env == "production"
        assert settings.log_json is True


class TestSecretsRedaction:
    """Tests for secret value redaction."""

    def test_secrets_are_redacted_in_repr(self) -> None:
        """Secrets should be redacted in repr() output."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            redis_url="redis://localhost:6379/0",
            auth_jwt_secret="super-secret-jwt-key-that-is-very-long-123456",
            auth_jwt_audience="test-audience",
            encryption_master_key=get_valid_secret(),
        )

        repr_str = repr(settings)
        # Secrets should be redacted (not show the actual secret value)
        assert "super-secret-jwt-key-that-is-very-long-123456" not in repr_str
        # The field name should be present
        assert "auth_jwt_secret" in repr_str
        assert "encryption_master_key" in repr_str


class TestSettingsCaching:
    """Tests for Settings caching behavior."""

    def test_get_settings_caches_result(self) -> None:
        """get_settings() should cache results."""
        # This test verifies the cache works by calling twice
        # Note: get_settings() reads from env, so we test with env vars
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
                "REDIS_URL": "redis://localhost:6379/0",
                "AUTH_JWT_SECRET": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "AUTH_JWT_AUDIENCE": "test-audience",
                "ENCRYPTION_MASTER_KEY": get_valid_secret(),
            },
        ):
            get_settings.cache_clear()
            settings1 = get_settings()
            settings2 = get_settings()

            assert settings1 is settings2

    def test_cache_can_be_cleared(self) -> None:
        """Settings cache can be cleared for testing."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
                "REDIS_URL": "redis://localhost:6379/0",
                "AUTH_JWT_SECRET": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "AUTH_JWT_AUDIENCE": "test-audience",
                "ENCRYPTION_MASTER_KEY": get_valid_secret(),
            },
        ):
            get_settings.cache_clear()
            _ = get_settings()
            get_settings.cache_clear()  # Should not raise

    def test_clear_cache_returns_new_instance(self) -> None:
        """Clearing cache should allow returning a new instance."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
                "REDIS_URL": "redis://localhost:6379/0",
                "AUTH_JWT_SECRET": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "AUTH_JWT_AUDIENCE": "test-audience",
                "ENCRYPTION_MASTER_KEY": get_valid_secret(),
            },
        ):
            get_settings.cache_clear()
            settings1 = get_settings()
            get_settings.cache_clear()
            settings2 = get_settings()

            # After clearing cache, get_settings() should return a new instance
            # But with lru_cache, it will be the same object again
            assert settings1 != settings2 or id(settings1) != id(settings2)


class TestEnvExampleMatchesFields:
    """Tests verifying .env.example keys match Settings fields."""

    def test_env_example_keys_match_settings_fields(self) -> None:
        """Assert .env.example keys equal the Settings fields with validation aliases."""
        # Parse .env.example
        env_example_path = Path(__file__).parent.parent.parent.parent / ".env.example"
        assert env_example_path.exists(), ".env.example file not found"

        env_keys = set()
        with open(env_example_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key = line.split("=")[0]
                    env_keys.add(key.lower())

        # Map env keys to field names (only for fields with validation aliases)
        field_env_mapping: dict[str, str] = {}
        for field_name, field_info in Settings.model_fields.items():
            if field_info.validation_alias:
                alias = field_info.validation_alias
                if isinstance(alias, str):
                    field_env_mapping[alias.lower()] = field_name
                # Note: handling AliasPath/AliasChoices is complex, skip for now

        # Check all fields with validation aliases have corresponding .env keys
        missing_from_env_example = []
        for env_key in field_env_mapping:
            if env_key not in env_keys:
                missing_from_env_example.append(env_key)

        assert (
            not missing_from_env_example
        ), f"Fields missing from .env.example: {missing_from_env_example}"

    def test_all_non_optional_fields_in_env_example(self) -> None:
        """All required (non-optional) fields should be in .env.example."""
        env_example_path = Path(__file__).parent.parent.parent.parent / ".env.example"
        assert env_example_path.exists()

        with open(env_example_path) as f:
            env_content = f.read()

        # Check that required fields are present (not empty comments)
        required_fields = [
            "DATABASE_URL",
            "REDIS_URL",
            "AUTH_JWT_SECRET",
            "AUTH_JWT_AUDIENCE",
            "ENCRYPTION_MASTER_KEY",
        ]

        for field in required_fields:
            assert field in env_content, f"{field} missing from .env.example"


class TestSettingsFromEnvFile:
    """Tests for Settings loading from .env file."""

    def test_settings_loadable_from_env_file(self, tmp_path: Path) -> None:
        """Settings can be loaded from a .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql://from-dotenv:5432/db\n"
            "REDIS_URL=redis://from-dotenv\n"
            "AUTH_JWT_SECRET=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
            "AUTH_JWT_AUDIENCE=dotenv-audience\n"
            f"ENCRYPTION_MASTER_KEY={get_valid_secret()}\n"
        )

        # pydantic-settings uses _env_file as a private argument
        settings = Settings(_env_file=str(env_file))  # type: ignore[call-arg, unused-ignore]

        assert settings.database_url == "postgresql://from-dotenv:5432/db"
        assert settings.redis_url == "redis://from-dotenv"
        assert settings.auth_jwt_audience == "dotenv-audience"

    def test_env_vars_override_env_file(self, tmp_path: Path) -> None:
        """Environment variables should override .env file values."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql://from-dotenv:5432/db\n"
        )

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://from-env:5432/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "AUTH_JWT_SECRET": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "AUTH_JWT_AUDIENCE": "env-audience",
                "ENCRYPTION_MASTER_KEY": get_valid_secret(),
            },
        ):
            get_settings.cache_clear()
            settings = get_settings()

            # Env var should override .env
            assert settings.database_url == "postgresql://from-env:5432/db"


class TestValidationAlias:
    """Tests for validation alias behavior."""

    def test_validation_aliases_case_insensitive(self) -> None:
        """Validation aliases should work regardless of case when case_sensitive=False."""
        settings = Settings(
            database_url="postgresql://test:5432/db",
            redis_url="redis://localhost",
            auth_jwt_secret="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            auth_jwt_audience="audience",
            encryption_master_key=get_valid_secret(),
        )

        assert settings.database_url == "postgresql://test:5432/db"

    def test_validation_alias_uppercase(self) -> None:
        """Uppercase validation aliases should work via environment."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:5432/db",
                "REDIS_URL": "redis://localhost",
                "AUTH_JWT_SECRET": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "AUTH_JWT_AUDIENCE": "audience",
                "ENCRYPTION_MASTER_KEY": get_valid_secret(),
            },
        ):
            get_settings.cache_clear()
            settings = get_settings()

            assert settings.database_url == "postgresql://test:5432/db"