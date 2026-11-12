"""Tests for the health check functionality.

Tests follow the separation of concerns:
- Schema tests: test_health_response patterns
- Repository tests: test the data access layer with mocked connections
- Service tests: test the business logic orchestration
- Route tests: test the HTTP endpoint
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from metis.core.error_handlers import register_error_handlers
from metis.modules.health.schemas import HealthResponse, HealthStatus


class TestHealthResponse:
    """Tests for the HealthResponse schema."""

    def test_health_response_is_valid(self) -> None:
        """HealthResponse should be created with valid data."""
        response = HealthResponse(
            status="ok",
            db="ok",
            redis="ok",
            version="abc123",
        )

        assert response.status == "ok"
        assert response.db == "ok"
        assert response.redis == "ok"
        assert response.version == "abc123"

    def test_health_response_with_down_db(self) -> None:
        """HealthResponse can represent a down database."""
        response = HealthResponse(
            status="down",
            db="down",
            redis="ok",
            version="abc123",
        )

        assert response.status == "down"
        assert response.db == "down"
        assert response.redis == "ok"


class TestPostgresRepository:
    """Tests for PostgreSQL repository functions."""

    @pytest.mark.asyncio
    async def test_query_postgres_success(self) -> None:
        """query_postgres should return True when query succeeds."""
        from metis.modules.health.repository import query_postgres

        with patch("metis.modules.health.repository.asyncpg.connect") as mock_connect:
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock(return_value="1")
            mock_conn.close = AsyncMock()
            mock_connect.return_value = mock_conn

            result = await query_postgres(
                dsn="postgresql://test:test@localhost:5432/test",
                query="SELECT 1",
                timeout_secs=1.0,
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_query_postgres_failure(self) -> None:
        """query_postgres should return False on connection failure."""
        from metis.modules.health.repository import query_postgres

        with patch("metis.modules.health.repository.asyncpg.connect") as mock_connect:
            mock_connect.side_effect = Exception("Connection refused")

            result = await query_postgres(
                dsn="postgresql://test:test@localhost:5432/test",
                query="SELECT 1",
                timeout_secs=1.0,
            )

            assert result is False


class TestRedisRepository:
    """Tests for Redis repository functions."""

    @pytest.mark.asyncio
    async def test_ping_redis_success(self) -> None:
        """ping_redis should return True when reachable."""
        from metis.modules.health.repository import ping_redis

        with patch("metis.modules.health.repository.redis.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.close = AsyncMock()
            mock_redis.return_value = mock_client

            result = await ping_redis(url="redis://localhost:6379/0", timeout_secs=1.0)

            assert result is True

    @pytest.mark.asyncio
    async def test_ping_redis_failure(self) -> None:
        """ping_redis should return False on connection failure."""
        from metis.modules.health.repository import ping_redis

        with patch("metis.modules.health.repository.redis.from_url") as mock_redis:
            mock_redis.side_effect = Exception("Connection refused")

            result = await ping_redis(url="redis://localhost:6379/0", timeout_secs=1.0)

            assert result is False


class TestServiceLayer:
    """Tests for service layer functions."""

    @pytest.mark.asyncio
    async def test_check_postgres_health_success(self) -> None:
        """check_postgres_health should return 'ok' when database is reachable."""
        from metis.modules.health.service import check_postgres_health

        with patch("metis.modules.health.service.check_postgres_connection", return_value="ok"):
            result = await check_postgres_health()

            assert result == HealthStatus.OK

    @pytest.mark.asyncio
    async def test_check_postgres_health_failure(self) -> None:
        """check_postgres_health should return 'down' when database is unreachable."""
        from metis.modules.health.service import check_postgres_health

        with patch("metis.modules.health.service.check_postgres_connection", return_value="down"):
            result = await check_postgres_health()

            assert result == HealthStatus.DOWN

    @pytest.mark.asyncio
    async def test_check_redis_health_success(self) -> None:
        """check_redis_health should return 'ok' when Redis is reachable."""
        from metis.modules.health.service import check_redis_health

        with patch("metis.modules.health.service.check_redis_connection", return_value="ok"):
            result = await check_redis_health()

            assert result == HealthStatus.OK

    @pytest.mark.asyncio
    async def test_check_redis_health_failure(self) -> None:
        """check_redis_health should return 'down' when Redis is unreachable."""
        from metis.modules.health.service import check_redis_health

        with patch("metis.modules.health.service.check_redis_connection", return_value="down"):
            result = await check_redis_health()

            assert result == HealthStatus.DOWN


class TestRunHealthChecks:
    """Tests for the run_health_checks orchestrator function."""

    @pytest.mark.asyncio
    async def test_run_health_checks_all_healthy(self) -> None:
        """run_health_checks should return healthy when both dependencies OK."""
        from metis.modules.health.service import run_health_checks

        with (
            patch(
                "metis.modules.health.service.check_postgres_health", return_value=HealthStatus.OK
            ),
            patch("metis.modules.health.service.check_redis_health", return_value=HealthStatus.OK),
            patch("metis.modules.health.service.get_version", return_value="abc123"),
        ):
            result = await run_health_checks()

            assert result.status == "ok"
            assert result.db == "ok"
            assert result.redis == "ok"
            assert result.version == "abc123"

    @pytest.mark.asyncio
    async def test_run_health_checks_db_down(self) -> None:
        """run_health_checks should return down when database fails."""
        from metis.modules.health.service import run_health_checks

        with (
            patch(
                "metis.modules.health.service.check_postgres_health", return_value=HealthStatus.DOWN
            ),
            patch("metis.modules.health.service.check_redis_health", return_value=HealthStatus.OK),
            patch("metis.modules.health.service.get_version", return_value="abc123"),
        ):
            result = await run_health_checks()

            assert result.status == "down"
            assert result.db == "down"
            assert result.redis == "ok"


class TestGetVersion:
    """Tests for the get_version utility function."""

    def test_get_version_returns_git_sha(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_version should return the git commit SHA when in a git repo."""
        from metis.modules.health.parse import get_git_version

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123\n"

        def mock_run(*args, **kwargs):
            return mock_result

        monkeypatch.setattr("metis.modules.health.parse.subprocess.run", mock_run)
        result = get_git_version()
        assert result == "abc123"

    def test_get_version_fallback_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_version should return 'unknown' on error."""
        from metis.modules.health.parse import get_git_version

        def mock_run(*args, **kwargs):
            raise Exception("git not found")

        monkeypatch.setattr("metis.modules.health.parse.subprocess.run", mock_run)
        result = get_git_version()
        assert result == "unknown"


class TestHealthRoute:
    """Tests for the /v1/health HTTP route (controller layer)."""

    def test_health_route_returns_200_when_healthy(self) -> None:
        """Health route should return 200 when all dependencies are healthy."""
        from metis.modules.health import router

        app = FastAPI()
        register_error_handlers(app)
        app.include_router(router)

        with (
            patch("metis.modules.health.service.check_postgres_health") as mock_db,
            patch("metis.modules.health.service.check_redis_health") as mock_redis,
            patch("metis.modules.health.service.get_version", return_value="abc123"),
        ):
            mock_db.return_value = HealthStatus.OK
            mock_redis.return_value = HealthStatus.OK

            client = TestClient(app)
            response = client.get("/v1/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["db"] == "ok"
            assert data["redis"] == "ok"
            assert data["version"] == "abc123"

    def test_health_route_returns_503_when_db_down(self) -> None:
        """Health route should return 503 when database is down."""
        from metis.modules.health import router

        app = FastAPI()
        register_error_handlers(app)
        app.include_router(router)

        with (
            patch("metis.modules.health.service.check_postgres_health") as mock_db,
            patch("metis.modules.health.service.check_redis_health") as mock_redis,
            patch("metis.modules.health.service.get_version", return_value="abc123"),
        ):
            mock_db.return_value = HealthStatus.DOWN
            mock_redis.return_value = HealthStatus.OK

            client = TestClient(app)
            response = client.get("/v1/health")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "down"
            assert data["db"] == "down"
            assert data["redis"] == "ok"

    def test_health_route_requires_no_auth(self) -> None:
        """Health route should work without Authorization header."""
        from metis.modules.health import router

        app = FastAPI()
        register_error_handlers(app)
        app.include_router(router)

        with (
            patch("metis.modules.health.service.check_postgres_health") as mock_db,
            patch("metis.modules.health.service.check_redis_health") as mock_redis,
            patch("metis.modules.health.service.get_version", return_value="abc123"),
        ):
            mock_db.return_value = HealthStatus.OK
            mock_redis.return_value = HealthStatus.OK

            client = TestClient(app)
            response = client.get("/v1/health")

            assert response.status_code == 200
