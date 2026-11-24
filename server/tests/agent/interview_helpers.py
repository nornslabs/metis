"""A scripted OpenAI-compatible LLM for the Interviewer tests, and builders for its replies.

Each chat call pops the next ``Reply``: text, tool calls or both. The real runner streams
(LangGraph's ``messages`` mode turns streaming on), so a request with ``"stream": true``
gets server-sent chunks; any other gets one JSON completion. Every request body is kept so
a test can check what the model was shown (an answer, recalled turns).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import count
from typing import TYPE_CHECKING, Any

import httpx

from metis.modules.research import EMBEDDING_DIMENSIONS

if TYPE_CHECKING:
    from collections.abc import Iterator

USAGE = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


@dataclass(frozen=True)
class Call:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class Reply:
    text: str = ""
    calls: tuple[Call, ...] = ()


def ask(question: str, topic: str, **extra: Any) -> Reply:
    """An ``ask_user`` call; ``extra`` adds ``options``, ``multi`` or ``allow_free_text``."""
    return Reply(calls=(Call("ask_user", {"question": question, "topic": topic, **extra}),))


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
    embeddings: bool = False
    embedding_inputs: list[int] = field(default_factory=list)
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
        if request.url.path.endswith("/embeddings"):
            return self._embeddings(body)
        self.bodies.append(body)
        if not self.script:
            return httpx.Response(500, json={"error": {"message": "script exhausted"}})
        reply = self.script.pop(0)
        if body.get("stream"):
            return self._stream(reply)
        return httpx.Response(200, json=self._completion(reply))

    def _embeddings(self, body: dict[str, Any]) -> httpx.Response:
        """Vectors of the size the research module stores, or a 404 like a provider without any."""
        if not self.embeddings:
            return httpx.Response(404, json={"error": {"message": "no embeddings here"}})
        texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
        self.embedding_inputs.append(len(texts))
        data = [
            {"object": "embedding", "index": i, "embedding": [0.01] * EMBEDDING_DIMENSIONS}
            for i in range(len(texts))
        ]
        usage = {"prompt_tokens": 3, "total_tokens": 3}
        return httpx.Response(
            200, json={"object": "list", "data": data, "model": "test-embed", "usage": usage}
        )

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
