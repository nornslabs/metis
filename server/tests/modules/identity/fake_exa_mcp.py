"""An in-process stand-in for Exa's hosted MCP server, for key-check tests.

A real MCP server (``FastMCP`` from the ``mcp`` SDK) with one
``web_search_exa`` tool, served over streamable HTTP through
``httpx.ASGITransport``. ``mode`` picks how it answers; it records the
``x-api-key`` header and the tool arguments it received.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import Receive, Scope, Send

from metis.adapters.mcp.exa import API_KEY_HEADER, SEARCH_TOOL

SLOW_TOOL_SECONDS = 1.0


class ExaMode(StrEnum):
    OK = "ok"
    BAD_KEY = "bad_key"  # what Exa really does: a tool error with "(401)" in its text
    TOOL_ERROR = "tool_error"
    HTTP_401 = "http_401"
    SLOW = "slow"
    UNREACHABLE = "unreachable"


class FakeExaMcp:
    def __init__(self) -> None:
        self.mode = ExaMode.OK
        self.api_keys: list[str | None] = []
        self.tool_calls: list[dict[str, Any]] = []
        self._server = FastMCP(
            "fake-exa",
            stateless_http=True,
            json_response=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        self._server.add_tool(self._web_search, name=SEARCH_TOOL)
        self._app = self._server.streamable_http_app()

    async def _web_search(self, query: str, objective: str, numResults: int = 10) -> str:  # noqa: N803 - Exa's field name
        self.tool_calls.append({"query": query, "objective": objective, "numResults": numResults})
        if self.mode is ExaMode.BAD_KEY:
            raise ValueError(f"{SEARCH_TOOL} error (401): Invalid API key.")
        if self.mode is ExaMode.TOOL_ERROR:
            raise ValueError(f"{SEARCH_TOOL} error (500): upstream failed")
        if self.mode is ExaMode.SLOW:
            await asyncio.sleep(SLOW_TOOL_SECONDS)
        return "Title: Example\nURL: https://example.com"

    async def _asgi(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self.mode is ExaMode.HTTP_401:
            await send({"type": "http.response.start", "status": 401, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return
        await self._app(scope, receive, send)

    def transport(self) -> httpx.AsyncBaseTransport:
        return _RecordingTransport(self, httpx.ASGITransport(app=self._asgi))

    @asynccontextmanager
    async def running(self) -> AsyncGenerator[FakeExaMcp]:
        """Run the MCP session manager (the app's lifespan) for the test.

        It runs in its own task: its anyio cancel scope must be entered and
        exited in one task, and pytest-asyncio sets fixtures up and tears them
        down in different tasks.
        """
        started, stop = asyncio.Event(), asyncio.Event()

        async def serve() -> None:
            async with self._server.session_manager.run():
                started.set()
                await stop.wait()

        task = asyncio.create_task(serve())
        await started.wait()
        try:
            yield self
        finally:
            stop.set()
            await task


class _RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, fake: FakeExaMcp, inner: httpx.AsyncBaseTransport) -> None:
        self._fake = fake
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self._fake.api_keys.append(request.headers.get(API_KEY_HEADER))
        if self._fake.mode is ExaMode.UNREACHABLE:
            raise httpx.ConnectError("no route to host", request=request)
        return await self._inner.handle_async_request(request)
