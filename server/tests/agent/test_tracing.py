"""Langfuse tracing is on only when its keys are set."""

from __future__ import annotations

import pytest

from metis.agent import tracing
from metis.agent.tracing import record_gate_span, tracing_callbacks
from metis.core.config import get_settings


def test_no_tracing_without_langfuse_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    get_settings.cache_clear()

    assert tracing_callbacks(get_settings()) == []
    get_settings.cache_clear()


def test_one_callback_when_langfuse_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:9")
    get_settings.cache_clear()

    assert len(tracing_callbacks(get_settings())) == 1
    get_settings.cache_clear()


GATE_FIELDS = {
    "specialist": "interviewer",
    "gate": "question",
    "decision": "skipped",
    "reason": "r",
}


def test_no_gate_span_without_langfuse_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    started: list[str] = []
    monkeypatch.setattr(tracing, "get_client", lambda: started.append("client"))

    record_gate_span(get_settings(), GATE_FIELDS)

    assert started == []
    get_settings.cache_clear()


def test_one_gate_span_with_the_decision_fields_when_langfuse_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    get_settings.cache_clear()
    spans: list[dict[str, object]] = []

    class FakeSpan:
        def end(self) -> None:
            spans[-1]["ended"] = True

    class FakeClient:
        def start_observation(self, **kwargs: object) -> FakeSpan:
            spans.append(dict(kwargs))
            return FakeSpan()

    monkeypatch.setattr(tracing, "get_client", lambda: FakeClient())

    record_gate_span(get_settings(), GATE_FIELDS)

    assert spans == [
        {"name": "gate:question", "as_type": "span", "metadata": GATE_FIELDS, "ended": True}
    ]
    get_settings.cache_clear()


def test_a_tracing_failure_never_reaches_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    get_settings.cache_clear()

    def broken() -> None:
        raise RuntimeError("langfuse down")

    monkeypatch.setattr(tracing, "get_client", broken)

    record_gate_span(get_settings(), GATE_FIELDS)
    get_settings.cache_clear()
