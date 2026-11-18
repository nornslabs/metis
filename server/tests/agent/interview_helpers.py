"""A scripted OpenAI-compatible LLM for the Interviewer tests, and builders for its replies.

Each chat call pops the next ``Reply``: text, tool calls or both. The real runner streams
(LangGraph's ``messages`` mode turns streaming on), so a request with ``"stream": true``
gets server-sent chunks; any other gets one JSON completion. Every request body is kept so
a test can check what the model was shown (an answer, recalled turns).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from itertools import count
from typing import Any

import httpx

USAGE = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


@dataclass(frozen=True)
class Call:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class Reply:
    text: str = ""
    calls: tuple[Call, ...] = ()


def ask(question: str, topic: str) -> Reply:
    return Reply(calls=(Call("ask_user", {"question": question, "topic": topic}),))


def note(topic: str, question: str, answer: str) -> Reply:
    args = {"topic": topic, "question": question, "answer": answer}
    return Reply(calls=(Call("save_interview_turn", args),))


def recall() -> Reply:
    return Reply(calls=(Call("recall_memory", {}),))


def finish(**findings: str) -> Reply:
    return Reply(calls=(Call("finish_interview", dict(findings)),))


@dataclass
class ScriptedLLM:
    """Answers chat calls from ``script`` in order; a call past its end is a 500."""

    script: list[Reply] = field(default_factory=list)
    bodies: list[dict[str, Any]] = field(default_factory=list)
    _ids: Iterator[int] = field(default_factory=count)

    def add(self, *replies: Reply) -> None:
        self.script.extend(replies)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    def shown(self, call: int) -> str:
        """Everything the model was sent in chat call ``call`` (0-based), as one string."""
        return json.dumps(self.bodies[call]["messages"])

    @property
    def calls(self) -> int:
        return len(self.bodies)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if not self.script:
            return httpx.Response(500, json={"error": {"message": "script exhausted"}})
        reply = self.script.pop(0)
        if body.get("stream"):
            return self._stream(reply)
        return httpx.Response(200, json=self._completion(reply))

    def _tool_calls(self, reply: Reply) -> list[dict[str, Any]]:
        return [
            {
                "id": f"call_{next(self._ids)}",
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.args)},
            }
            for call in reply.calls
        ]

    def _completion(self, reply: Reply) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant", "content": reply.text or None}
        if reply.calls:
            message["tool_calls"] = self._tool_calls(reply)
        return {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1,
            "model": "test-model",
            "choices": [{"index": 0, "message": message, "finish_reason": _finish(reply)}],
            "usage": USAGE,
        }

    def _stream(self, reply: Reply) -> httpx.Response:
        delta: dict[str, Any] = {"role": "assistant", "content": reply.text or ""}
        if reply.calls:
            delta["tool_calls"] = [
                {"index": i, **call} for i, call in enumerate(self._tool_calls(reply))
            ]
        chunks = [
            _chunk([{"index": 0, "delta": delta, "finish_reason": None}]),
            _chunk([{"index": 0, "delta": {}, "finish_reason": _finish(reply)}]),
            _chunk([], usage=USAGE),
        ]
        lines = [f"data: {json.dumps(c)}\n\n" for c in chunks] + ["data: [DONE]\n\n"]
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content="".join(lines).encode()
        )


def _finish(reply: Reply) -> str:
    return "tool_calls" if reply.calls else "stop"


def _chunk(choices: list[dict[str, Any]], usage: dict[str, int] | None = None) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test-model",
        "choices": choices,
    }
    if usage is not None:
        chunk["usage"] = usage
    return chunk
