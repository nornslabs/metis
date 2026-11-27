"""FlagsmithProvider: mapping to the SDK, defaults on every failure path, lifecycle."""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from flagsmith.exceptions import FlagsmithAPIError, FlagsmithFeatureDoesNotExistError

from metis.adapters.feature_flags.flagsmith import FlagsmithProvider
from metis.core.ports import FlagContext

CONTEXT = FlagContext(environment="test")


@dataclass
class FakeFlag:
    enabled: bool = True
    value: Any = None


class FakeFlags:
    def __init__(self, flags: dict[str, FakeFlag], error: Exception | None = None) -> None:
        self._flags = flags
        self._error = error

    def get_flag(self, feature_name: str) -> FakeFlag:
        if self._error is not None:
            raise self._error
        if feature_name not in self._flags:
            raise FlagsmithFeatureDoesNotExistError("missing")
        return self._flags[feature_name]


class FakeClient:
    def __init__(self, flags: dict[str, FakeFlag], error: Exception | None = None) -> None:
        self.flags = FakeFlags(flags, error)
        self.identity_calls: list[tuple[str, dict[str, Any]]] = []
        self.environment_calls = 0
        self.close_calls = 0
        self.delay = 0.0

    def get_identity_flags(self, identifier: str, traits: dict[str, Any]) -> FakeFlags:
        time.sleep(self.delay)
        self.identity_calls.append((identifier, traits))
        return self.flags

    def get_environment_flags(self) -> FakeFlags:
        self.environment_calls += 1
        return self.flags

    def close(self) -> None:
        self.close_calls += 1


def provider_for(client: FakeClient, **kwargs: Any) -> FlagsmithProvider:
    return FlagsmithProvider(
        "ser.test", "https://flags.example/api/v1/", client_factory=lambda: client, **kwargs
    )


async def test_boolean_flag_on_off_and_missing_use_the_caller_default() -> None:
    client = FakeClient({"on": FakeFlag(True), "off": FakeFlag(False)})
    provider = provider_for(client)

    assert await provider.is_enabled("on", CONTEXT) is True
    assert await provider.is_enabled("off", CONTEXT, True) is False
    assert await provider.is_enabled("missing", CONTEXT, True) is True
    assert await provider.is_enabled("missing", CONTEXT) is False


async def test_string_values_and_their_defaults() -> None:
    client = FakeClient(
        {
            "text": FakeFlag(True, "gpt"),
            "number": FakeFlag(True, 5),
            "none": FakeFlag(True, None),
            "empty": FakeFlag(True, ""),
            "disabled": FakeFlag(False, "gpt"),
        }
    )
    provider = provider_for(client)

    assert await provider.get_string("text", CONTEXT, "d") == "gpt"
    assert await provider.get_string("number", CONTEXT, "d") == "5"
    assert await provider.get_string("none", CONTEXT, "d") == "d"
    assert await provider.get_string("empty", CONTEXT, "d") == "d"
    assert await provider.get_string("disabled", CONTEXT, "d") == "d"
    assert await provider.get_string("missing", CONTEXT, "d") == "d"


async def test_json_object_list_and_defaults(caplog: pytest.LogCaptureFixture) -> None:
    client = FakeClient(
        {
            "obj": FakeFlag(True, '{"a": 1}'),
            "list": FakeFlag(True, "[1, 2]"),
            "bad": FakeFlag(True, "not-json-secret"),
            "empty": FakeFlag(True, "  "),
            "disabled": FakeFlag(False, '{"a": 1}'),
        }
    )
    provider = provider_for(client)

    assert await provider.get_json("obj", CONTEXT, None) == {"a": 1}
    assert await provider.get_json("list", CONTEXT, None) == [1, 2]
    assert await provider.get_json("bad", CONTEXT, {"d": 1}) == {"d": 1}
    assert await provider.get_json("bad", CONTEXT, {"d": 1}) == {"d": 1}
    assert await provider.get_json("empty", CONTEXT, "d") == "d"
    assert await provider.get_json("disabled", CONTEXT, "d") == "d"
    assert await provider.get_json("missing", CONTEXT, "d") == "d"
    assert "not-json-secret" not in caplog.text


async def test_identity_is_the_workspace_with_attributes_environment_and_user_traits() -> None:
    client = FakeClient({"f": FakeFlag()})
    workspace_id, user_id = uuid4(), uuid4()
    context = FlagContext(
        environment="prod",
        workspace_id=workspace_id,
        user_id=user_id,
        custom_attributes={"plan": "pro"},
    )

    await provider_for(client).is_enabled("f", context)

    assert client.identity_calls == [
        (str(workspace_id), {"plan": "pro", "environment": "prod", "user_id": str(user_id)})
    ]


async def test_identity_falls_back_to_user_then_to_environment_flags() -> None:
    client = FakeClient({"f": FakeFlag()})
    user_id = uuid4()
    provider = provider_for(client)

    await provider.is_enabled("f", FlagContext(environment="t", user_id=user_id))
    await provider.is_enabled("f", CONTEXT)

    assert [call[0] for call in client.identity_calls] == [str(user_id)]
    assert client.environment_calls == 1


async def test_an_sdk_error_gives_the_default_and_never_raises() -> None:
    client = FakeClient({}, error=FlagsmithAPIError("boom"))
    provider = provider_for(client)

    assert await provider.is_enabled("f", CONTEXT, True) is True
    assert await provider.get_string("f", CONTEXT, "d") == "d"
    assert await provider.get_json("f", CONTEXT, 1) == 1


async def test_cancellation_is_not_swallowed() -> None:
    client = FakeClient({"f": FakeFlag()})
    client.delay = 0.2
    context = FlagContext(environment="test", workspace_id=uuid4())
    task = asyncio.create_task(provider_for(client).is_enabled("f", context))
    await asyncio.sleep(0.05)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_failed_client_build_retries_only_after_the_cooldown() -> None:
    now = [0.0]
    builds: list[int] = []
    client = FakeClient({"f": FakeFlag()})

    def factory() -> FakeClient:
        builds.append(1)
        if len(builds) == 1:
            raise OSError("unreachable")
        return client

    provider = FlagsmithProvider(
        "ser.test", "https://flags.example/api/v1/", client_factory=factory, clock=lambda: now[0]
    )

    assert await provider.is_enabled("f", CONTEXT, False) is False
    now[0] = 10.0
    assert await provider.is_enabled("f", CONTEXT, False) is False
    assert len(builds) == 1
    now[0] = 31.0
    assert await provider.is_enabled("f", CONTEXT, False) is True
    assert len(builds) == 2


async def test_the_client_is_built_once_for_concurrent_first_reads() -> None:
    builds: list[int] = []
    client = FakeClient({"f": FakeFlag()})

    def factory() -> FakeClient:
        builds.append(1)
        time.sleep(0.05)
        return client

    provider = FlagsmithProvider("ser.test", "https://x/", client_factory=factory)

    await asyncio.gather(*(provider.is_enabled("f", CONTEXT) for _ in range(5)))

    assert len(builds) == 1


async def test_close_stops_the_client_is_safe_twice_and_reads_give_defaults() -> None:
    client = FakeClient({"f": FakeFlag()})
    provider = provider_for(client)
    await provider.is_enabled("f", CONTEXT)

    await provider.close()
    await provider.close()

    assert client.close_calls == 1
    assert await provider.is_enabled("f", CONTEXT, False) is False


async def test_close_before_any_read_is_safe() -> None:
    await provider_for(FakeClient({})).close()


async def test_a_slow_client_does_not_block_the_event_loop() -> None:
    client = FakeClient({"f": FakeFlag()})
    client.delay = 0.3
    provider = provider_for(client)
    ticks: list[int] = []

    async def ticker() -> None:
        for _ in range(5):
            ticks.append(1)
            await asyncio.sleep(0.02)

    context = FlagContext(environment="test", workspace_id=uuid4())

    await asyncio.gather(provider.is_enabled("f", context), ticker())

    assert len(ticks) == 5
    assert threading.current_thread() is threading.main_thread()


def test_a_client_side_key_is_refused() -> None:
    with pytest.raises(ValueError, match="server-side"):
        FlagsmithProvider("client-secret", "https://x/")


async def test_a_cancelled_first_read_does_not_leak_a_second_client() -> None:
    clients: list[FakeClient] = []

    def factory() -> FakeClient:
        time.sleep(0.15)
        client = FakeClient({"f": FakeFlag()})
        clients.append(client)
        return client

    provider = FlagsmithProvider("ser.test", "https://x/", client_factory=factory)
    first = asyncio.create_task(provider.is_enabled("f", CONTEXT))
    await asyncio.sleep(0.03)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    assert await provider.is_enabled("f", CONTEXT) is True
    await provider.close()

    assert len(clients) == 1
    assert clients[0].close_calls == 1


async def test_invalid_json_warns_once_per_key_even_after_the_throttle_window(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = [0.0]
    client = FakeClient({"bad": FakeFlag(True, "{")})
    provider = provider_for(client, clock=lambda: now[0])

    await provider.get_json("bad", CONTEXT, None)
    now[0] = 500.0
    await provider.get_json("bad", CONTEXT, None)

    assert caplog.text.count("feature_flags.invalid_value") <= 1
