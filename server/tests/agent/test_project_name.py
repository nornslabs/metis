"""The model-written project name: the name check, the title fallback, and the call that
never fails the export."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from metis.agent.specialists.integrator import _project_name, _Source
from metis.agent.tools.project_name import (
    MAX_SUGGESTED_NAME_CHARS,
    clean_name,
    fallback_name,
    suggest_project_name,
)
from metis.core.errors import UpstreamError

TITLE = "An AI assistant that helps small restaurant owners plan their weekly menus"


class FakeModel:
    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.calls = 0

    async def ainvoke(self, messages: Any, config: Any = None) -> AIMessage:
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return AIMessage(content=self.reply)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value


class FakeGateway:
    def __init__(self, model: FakeModel) -> None:
        self.model = model

    async def chat_model(self, session: Any, purpose: str) -> FakeModel:
        return self.model


@asynccontextmanager
async def _open_session(_workspace_id: Any) -> Any:
    yield None


def _source(project_name: str | None = None) -> Any:
    source = _Source.__new__(_Source)
    source.project_name = project_name
    source.title = TITLE
    source.raw_text = "Menus for restaurants."
    source.spec_text = "# Spec\n\nPlans menus."
    return source


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("Menu Pilot", "Menu Pilot"),
        ('  "Menu Pilot."  \n', "Menu Pilot"),
        ("Menuly", "Menuly"),
        ("(Menu Pilot)", "Menu Pilot"),
    ],
)
def test_a_one_or_two_word_reply_is_the_name(reply: str, expected: str) -> None:
    assert clean_name(reply) == expected


@pytest.mark.parametrize(
    "reply",
    ["", "   ", "Menu Pilot Pro", "x" * (MAX_SUGGESTED_NAME_CHARS + 1), "Menu\nPilot", '""'],
)
def test_a_reply_that_is_not_a_short_name_is_refused(reply: str) -> None:
    assert clean_name(reply) is None


def test_the_fallback_is_the_first_two_words_of_the_title_within_the_limit() -> None:
    assert fallback_name(TITLE) == "An AI"
    assert len(fallback_name("x" * 100)) <= MAX_SUGGESTED_NAME_CHARS
    assert fallback_name("") == ""


async def test_a_valid_reply_is_the_suggested_name() -> None:
    name = await suggest_project_name(
        FakeModel("Menu Pilot"), idea_title=TITLE, raw_text="", spec_text=""
    )

    assert name == "Menu Pilot"


@pytest.mark.parametrize(
    "model", [None, FakeModel(UpstreamError("down")), FakeModel(""), FakeModel("A Long Sentence")]
)
async def test_a_failed_or_invalid_call_gives_the_title_fallback(model: FakeModel | None) -> None:
    name = await suggest_project_name(model, idea_title=TITLE, raw_text="", spec_text="")

    assert name == "An AI"


async def test_a_saved_name_is_used_and_no_model_call_is_made() -> None:
    model = FakeModel("Other Name")

    name = await _project_name(
        _open_session,
        FakeRedis(),
        FakeGateway(model),
        uuid4(),
        uuid4(),
        _source("Menu Pilot"),  # type: ignore[arg-type]
    )

    assert name == "Menu Pilot"
    assert model.calls == 0


async def test_the_suggestion_is_made_once_per_run() -> None:
    model = FakeModel("Menu Pilot")
    redis, run_id = FakeRedis(), uuid4()

    first = await _project_name(
        _open_session,
        redis,
        FakeGateway(model),
        uuid4(),
        run_id,
        _source(),  # type: ignore[arg-type]
    )
    again = await _project_name(
        _open_session,
        redis,
        FakeGateway(model),
        uuid4(),
        run_id,
        _source(),  # type: ignore[arg-type]
    )

    assert first == again == "Menu Pilot"
    assert model.calls == 1
