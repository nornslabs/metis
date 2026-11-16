"""Langfuse tracing is on only when its keys are set."""

from __future__ import annotations

import pytest

from metis.agent.tracing import tracing_callbacks
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
