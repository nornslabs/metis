"""A model that replays recorded ``submit_scores`` answers, for the offline harness check.

``recorded.jsonl`` holds one line per case and run: ``{"case": id, "run": 1, "params": [...]}``,
the arguments the Scorer's ``submit_scores`` tool takes. The replay works out which case a
request belongs to from the idea title in the seed, and which run from how many fresh starts
that case has had (a request that already carries a tool result is a retry inside the same run
and is answered with the same recording). A case or run with no recording is a 500.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from itertools import count
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

RECORDED_PATH = Path(__file__).parent / "scoring" / "recorded.jsonl"
SUBMIT_TOOL = "submit_scores"
TITLE_MARKER = "Idea title: "
USAGE = {"prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500}


class Recording(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case: str
    run: int
    params: list[dict[str, Any]]


def load_recordings(path: Path = RECORDED_PATH) -> dict[tuple[str, int], Recording]:
    recordings = [
        Recording.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {(r.case, r.run): r for r in recordings}


class RecordedLLM:
    """An OpenAI-compatible endpoint (``httpx.MockTransport``) answering from recordings."""

    def __init__(
        self, recordings: Mapping[tuple[str, int], Recording], case_by_title: Mapping[str, str]
    ) -> None:
        self._recordings = recordings
        self._case_by_title = case_by_title
        self._starts: Counter[str] = Counter()
        self._ids = count(1)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        case = self._case_of(body["messages"])
        if case is None:
            return _error("no known idea title in the request")
        if not any(m.get("role") == "tool" for m in body["messages"]):
            self._starts[case] += 1
        recording = self._recordings.get((case, self._starts[case]))
        if recording is None:
            return _error(f"no recording for {case} run {self._starts[case]}")
        call = {
            "id": f"call_{next(self._ids)}",
            "type": "function",
            "function": {
                "name": SUBMIT_TOOL,
                "arguments": json.dumps({"params": recording.params}),
            },
        }
        return _stream(call) if body.get("stream") else _completion(call)

    def _case_of(self, messages: list[dict[str, Any]]) -> str | None:
        text = json.dumps(messages)
        for title, case in self._case_by_title.items():
            if f"{TITLE_MARKER}{title}" in text:
                return case
        return None


def _error(message: str) -> httpx.Response:
    return httpx.Response(500, json={"error": {"message": message}})


def _completion(call: dict[str, Any]) -> httpx.Response:
    message = {"role": "assistant", "content": None, "tool_calls": [call]}
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-rec",
            "object": "chat.completion",
            "created": 1,
            "model": "recorded",
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls"}],
            "usage": USAGE,
        },
    )


def _stream(call: dict[str, Any]) -> httpx.Response:
    delta = {"role": "assistant", "content": "", "tool_calls": [{"index": 0, **call}]}
    chunks = [
        _chunk([{"index": 0, "delta": delta, "finish_reason": None}]),
        _chunk([{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]),
        _chunk([], usage=USAGE),
    ]
    lines = [f"data: {json.dumps(c)}\n\n" for c in chunks] + ["data: [DONE]\n\n"]
    return httpx.Response(
        200, headers={"content-type": "text/event-stream"}, content="".join(lines).encode()
    )


def _chunk(choices: list[dict[str, Any]], usage: dict[str, int] | None = None) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "id": "chatcmpl-rec",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "recorded",
        "choices": choices,
    }
    if usage is not None:
        chunk["usage"] = usage
    return chunk
