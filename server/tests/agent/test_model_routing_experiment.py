"""Model routing experiment: strategy exposure in the gateway, conversion on success."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent import runner
from metis.agent.llm import LLMGateway
from metis.core.config import get_settings
from metis.core.errors import ProviderNotConfiguredError
from metis.core.ports import FlagContext
from metis.modules import ideas
from tests.agent.llm_helpers import LLM_MODEL, FakeLLMServer, make_run, workspace_with_key

_TEST_SETTINGS_ENV = {
    "ENCRYPTION_MASTER_KEY": "lmnZiTdYDe6qnwh5yiWxEBRCzEcA/VCxuwBHAhzWnok=",
    "DATABASE_URL": "postgresql+asyncpg://metis_app:test@localhost:5432/metis",
    "REDIS_URL": "redis://localhost:6379/15",
}


class RecordingFlags:
    """A fake provider: serves canned values and records exposures and events."""

    def __init__(
        self,
        values: dict[str, Any] | None = None,
        *,
        variant: str = "",
        variant_error: Exception | None = None,
        track_error: Exception | None = None,
    ) -> None:
        self.values = values or {}
        self.variant = variant
        self.variant_error = variant_error
        self.track_error = track_error
        self.exposures: list[str] = []
        self.events: list[tuple[str, FlagContext]] = []

    async def is_enabled(self, key: str, context: FlagContext, default: bool = False) -> bool:
        return bool(self.values.get(key, default))

    async def get_string(self, key: str, context: FlagContext, default: str) -> str:
        return str(self.values.get(key, default))

    async def get_json(self, key: str, context: FlagContext, default: Any) -> Any:
        return self.values.get(key, default)

    async def get_experiment_variant(self, key: str, context: FlagContext, default: str) -> str:
        self.exposures.append(key)
        if self.variant_error is not None:
            raise self.variant_error
        return self.variant or default

    async def track_event(self, name: str, context: FlagContext) -> None:
        if self.track_error is not None:
            raise self.track_error
        self.events.append((name, context))

    async def close(self) -> None:
        return None


def _gateway(
    flags: RecordingFlags,
    workspace_id: UUID,
    run_id: UUID,
    sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> LLMGateway:
    return LLMGateway(
        workspace_id, run_id, sessions=sessions, http_client=server.client(), flags=flags
    )


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _TEST_SETTINGS_ENV.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()


ROUTES = {
    "model_routing": {"default": "plain-model"},
    "model_routing_cost_optimized": {"default": "cheap-model"},
    "model_routing_quality_optimized": {"default": "best-model"},
    "model_routing_balanced": {"default": "mid-model"},
}


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("cost_optimized", "cheap-model"),
        ("quality_optimized", "best-model"),
        ("balanced", "mid-model"),
        ("", "plain-model"),
        ("something_else", "plain-model"),
    ],
)
async def test_the_variation_picks_its_routing_and_unset_or_unknown_uses_model_routing(
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
    variant: str,
    expected: str,
) -> None:
    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)
    flags = RecordingFlags({**ROUTES}, variant=variant)
    gateway = _gateway(flags, workspace_id, run_id, app_sessions, server)

    async with app_sessions() as session:
        model = await gateway.chat_model(session, "interview")
    await model.ainvoke([HumanMessage("hi")])

    assert f'"model":"{expected}"' in server.requests[0].read().decode()


async def test_a_missing_strategy_flag_falls_back_to_model_routing(
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)
    flags = RecordingFlags({"model_routing": ROUTES["model_routing"]}, variant="balanced")
    gateway = _gateway(flags, workspace_id, run_id, app_sessions, server)

    async with app_sessions() as session:
        model = await gateway.chat_model(session, "interview")
    await model.ainvoke([HumanMessage("hi")])

    assert '"model":"plain-model"' in server.requests[0].read().decode()


async def test_a_failing_variant_read_uses_model_routing(
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)
    flags = RecordingFlags({**ROUTES}, variant_error=RuntimeError("down"))
    gateway = _gateway(flags, workspace_id, run_id, app_sessions, server)

    async with app_sessions() as session:
        model = await gateway.chat_model(session, "interview")
    await model.ainvoke([HumanMessage("hi")])

    assert '"model":"plain-model"' in server.requests[0].read().decode()


async def test_with_no_routing_flags_the_saved_model_is_used(
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)
    flags = RecordingFlags(variant="balanced")
    gateway = _gateway(flags, workspace_id, run_id, app_sessions, server)

    async with app_sessions() as session:
        model = await gateway.chat_model(session, "interview")
    await model.ainvoke([HumanMessage("hi")])

    assert f'"model":"{LLM_MODEL}"' in server.requests[0].read().decode()


async def test_exposure_is_recorded_once_per_run(
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)
    flags = RecordingFlags({**ROUTES}, variant="balanced")
    gateway = _gateway(flags, workspace_id, run_id, app_sessions, server)

    async with app_sessions() as session:
        await gateway.chat_model(session, "interview")
        await gateway.chat_model(session, "interview")
        await gateway.chat_model(session, "scoring", tier="free")

    assert flags.exposures == ["model_routing_strategy"]


async def test_no_exposure_when_the_llm_kill_switch_is_off() -> None:
    flags = RecordingFlags({"llm_enabled": False}, variant="balanced")
    gateway = LLMGateway(uuid4(), uuid4(), flags=flags)

    with pytest.raises(ProviderNotConfiguredError):
        await gateway.chat_model(None, "interview")  # type: ignore[arg-type]

    assert flags.exposures == []


async def test_an_empty_variation_means_no_strategy() -> None:
    flags = RecordingFlags(variant="")
    gateway = LLMGateway(uuid4(), uuid4(), flags=flags)

    assert await gateway._routing_strategy() is None  # noqa: SLF001
    assert flags.exposures == ["model_routing_strategy"]


# ------------------------------------------------------------------ conversion
class _Publisher:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    async def status(self, value: str) -> None:
        self.statuses.append(value)

    async def publish(self, *args: Any) -> None:
        return None


@asynccontextmanager
async def _no_session(*args: Any) -> AsyncIterator[None]:
    yield None


async def _noop(*args: Any, **kwargs: Any) -> None:
    return None


def _patch_run_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "_scoped", _no_session)
    monkeypatch.setattr(ideas, "mark_succeeded", _noop)
    monkeypatch.setattr(ideas, "mark_cancelled", _noop)
    monkeypatch.setattr(ideas, "mark_awaiting_user", _noop)
    monkeypatch.setattr(runner, "_record_failure", _noop)


class _Run:
    def __init__(self) -> None:
        self.workspace_id = uuid4()
        self.id = uuid4()


def _deps(flags: RecordingFlags) -> runner.RunnerDeps:
    return runner.RunnerDeps(sessions=None, database_url="", flags=flags)  # type: ignore[arg-type]


async def test_a_succeeded_run_records_one_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run_store(monkeypatch)
    flags = RecordingFlags()
    run = _Run()

    await runner._settle(_deps(flags), _Publisher(), run, runner.Outcome("done"))  # type: ignore[arg-type]  # noqa: SLF001

    assert [name for name, _ in flags.events] == ["run_completed_successfully"]
    assert flags.events[0][1].workspace_id == run.workspace_id


@pytest.mark.parametrize(
    "outcome",
    [
        runner.Outcome("done", last_error="step_limit"),
        runner.Outcome("cancelled"),
        runner.Outcome("interrupted", interrupt={"kind": "question"}),
        runner.Outcome("lock_lost"),
    ],
)
async def test_other_outcomes_record_no_conversion(
    monkeypatch: pytest.MonkeyPatch, outcome: runner.Outcome
) -> None:
    _patch_run_store(monkeypatch)
    flags = RecordingFlags()

    await runner._settle(_deps(flags), _Publisher(), _Run(), outcome)  # type: ignore[arg-type]  # noqa: SLF001

    assert flags.events == []


async def test_a_tracking_failure_does_not_change_the_run_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_run_store(monkeypatch)
    flags = RecordingFlags(track_error=RuntimeError("boom"))
    publisher = _Publisher()

    await runner._settle(_deps(flags), publisher, _Run(), runner.Outcome("done"))  # type: ignore[arg-type]  # noqa: SLF001

    assert publisher.statuses == ["succeeded"]
