"""Run-scoped Exa tools backed by the hosted MCP server."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

import httpx
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.tools import load_mcp_tools
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import UpstreamError
from metis.core.events import RunEventType, publish
from metis.helpers.http import ClientFactory, FailureReason, provider_error
from metis.helpers.mcp import open_mcp_session
from metis.modules.identity import ProviderKind, get_key_for_use

PROVIDER = "exa"
EXA_MCP_URL = "https://mcp.exa.ai/mcp"
API_KEY_HEADER = "x-api-key"
SEARCH_TOOL = "web_search_exa"
FETCH_TOOL = "web_fetch_exa"
TOOL_TIMEOUT_SECONDS = 20
MAX_RESULTS = 10
MAX_FETCH_CHARS = 4_000
CACHE_TTL_SECONDS = 60 * 60
RETRY_DELAYS = (0.1, 0.2)
RESEARCHER_TOOLS = frozenset({SEARCH_TOOL, FETCH_TOOL})
SEARCH_ONLY_TOOLS = frozenset({SEARCH_TOOL})


@dataclass(frozen=True)
class ResearchHit:
    url: str
    title: str
    published_at: str | None
    snippet: str
    source: str = PROVIDER


def allowed_exa_tools(specialist: str) -> frozenset[str]:
    """The Exa allow-list for a specialist."""
    if specialist == "researcher":
        return RESEARCHER_TOOLS
    if specialist in {"scorer", "advisor"}:
        return SEARCH_ONLY_TOOLS
    return frozenset()


def exa_tools_for(specialist: str, tools: Mapping[str, BaseTool]) -> list[BaseTool]:
    """Select only the loaded Exa tools allowed for this specialist."""
    allowed = allowed_exa_tools(specialist)
    return [tool for name, tool in tools.items() if name in allowed]


@asynccontextmanager
async def load_exa_tools(
    session: AsyncSession,
    workspace_id: UUID,
    run_id: UUID,
    redis: Redis,
    make_client: ClientFactory,
) -> AsyncGenerator[dict[str, BaseTool]]:
    """Open the workspace's authenticated Exa MCP session for one run."""
    credentials = await get_key_for_use(session, workspace_id, ProviderKind.EXA)
    async with (
        make_client({API_KEY_HEADER: credentials.api_key}) as http,
        open_mcp_session(http, EXA_MCP_URL, PROVIDER) as mcp_session,
    ):
        loaded = await load_mcp_tools(mcp_session, handle_tool_errors=False)
        raw = {tool.name: tool for tool in loaded if tool.name in RESEARCHER_TOOLS}
        if set(raw) != RESEARCHER_TOOLS:
            raise provider_error(PROVIDER, FailureReason.BAD_RESPONSE)
        yield {
            name: _wrap_tool(tool, name, str(run_id), redis)
            for name, tool in raw.items()
        }


def _wrap_tool(tool: BaseTool, name: str, run_id: str, redis: Redis) -> BaseTool:
    async def invoke(**arguments: Any) -> Any:
        args = dict(arguments)
        if name == SEARCH_TOOL:
            args["numResults"] = min(MAX_RESULTS, max(1, int(args.get("numResults", MAX_RESULTS))))
        key = _cache_key(run_id, name, args)
        cached = await redis.get(key)
        if cached is not None:
            normalized = json.loads(cached)
        else:
            result: Any = None
            for attempt in range(len(RETRY_DELAYS) + 1):
                try:
                    async with asyncio.timeout(TOOL_TIMEOUT_SECONDS):
                        result = await tool.ainvoke(args)
                    break
                except Exception as exc:  # noqa: BLE001 - MCP errors are normalized below
                    reason = _tool_failure_reason(exc)
                    retryable = {FailureReason.RATE_LIMITED, FailureReason.SERVER_ERROR}
                    if reason not in retryable or attempt == len(RETRY_DELAYS):
                        raise provider_error(PROVIDER, reason) from None
                    await asyncio.sleep(RETRY_DELAYS[attempt])

            if name == SEARCH_TOOL:
                normalized = [asdict(hit) for hit in _research_hits(result)[:MAX_RESULTS]]
            else:
                normalized = _fetch_result(result, args)
            await redis.set(key, json.dumps(normalized), ex=CACHE_TTL_SECONDS)

        count = (
            len(normalized)
            if isinstance(normalized, list)
            else int(bool(normalized.get("content")))
        )
        query = str(args.get("query", args.get("url", "")))
        await publish(
            run_id,
            RunEventType.TOOL_CALL,
            {"query": query, "result_count": count},
            redis=redis,
        )
        return normalized

    return StructuredTool.from_function(
        coroutine=invoke,
        name=name,
        description=tool.description or "",
        args_schema=tool.args_schema,
    )


def _cache_key(run_id: str, tool_name: str, args: Mapping[str, Any]) -> str:
    encoded = json.dumps(args, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    return f"agent:exa:{run_id}:{tool_name}:{digest}"


def _tool_failure_reason(exc: Exception) -> FailureReason:
    if isinstance(exc, UpstreamError):
        try:
            return FailureReason(str(exc.meta.get("reason", "bad_response")))
        except ValueError:
            return FailureReason.BAD_RESPONSE
    if isinstance(exc, TimeoutError | httpx.TimeoutException):
        return FailureReason.TIMEOUT
    if isinstance(exc, httpx.TransportError):
        return FailureReason.UNREACHABLE
    message = str(exc)
    if "(401)" in message or "(403)" in message:
        return FailureReason.UNAUTHORIZED
    if re.search(r"\(?429\)?", message):
        return FailureReason.RATE_LIMITED
    if re.search(r"\(?(50[0-9])\)?", message):
        return FailureReason.SERVER_ERROR
    return FailureReason.BAD_RESPONSE


def _research_hits(result: Any) -> list[ResearchHit]:
    """Convert Exa MCP output into small, URL-bearing research records."""
    value = _structured_value(result)
    rows = _find_result_rows(value)
    if not rows and isinstance(value, str):
        rows = _parse_text_hits(value)
    hits: list[ResearchHit] = []
    for row in rows:
        url = row.get("url") or row.get("link")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        hits.append(
            ResearchHit(
                url=url,
                title=str(row.get("title") or ""),
                published_at=_optional_text(row.get("publishedDate", row.get("published_at"))),
                snippet=str(
                    row.get("snippet") or row.get("summary") or row.get("text") or ""
                )[:MAX_FETCH_CHARS],
            )
        )
    return hits


def _structured_value(result: Any) -> Any:
    if isinstance(result, tuple) and len(result) == 2:
        _content, artifact = result
        if artifact is not None:
            structured = getattr(artifact, "structured_content", None)
            if structured is not None:
                return structured
    if isinstance(result, list):
        blocks = [item.get("text", "") for item in result if isinstance(item, Mapping)]
        value = "\n".join(str(block) for block in blocks)
    elif isinstance(result, str):
        value = result
    else:
        value = result
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _find_result_rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        for key in ("results", "items", "data"):
            if key in value:
                rows = _find_result_rows(value[key])
                if rows:
                    return rows
        return [value] if "url" in value or "link" in value else []
    if isinstance(value, list):
        return [row for item in value for row in _find_result_rows(item)]
    return []


def _parse_text_hits(value: str) -> list[Mapping[str, Any]]:
    chunks = re.split(r"(?=Title:\s*)", value)
    rows: list[Mapping[str, Any]] = []
    for chunk in chunks:
        fields = dict(
            re.findall(r"^(Title|URL|Published Date|Summary|Snippet):\s*(.*)$", chunk, re.M)
        )
        if fields.get("URL"):
            rows.append({
                "url": fields["URL"],
                "title": fields.get("Title", ""),
                "publishedDate": fields.get("Published Date"),
                "snippet": fields.get("Snippet") or fields.get("Summary", ""),
            })
    return rows


def _fetch_result(result: Any, args: Mapping[str, Any]) -> dict[str, str]:
    value = _structured_value(result)
    if isinstance(value, Mapping):
        url = str(value.get("url") or args.get("url") or "")
        content = str(value.get("content") or value.get("text") or value.get("textContent") or "")
    else:
        url = str(args.get("url", ""))
        content = str(value)
    return {"url": url, "content": content[:MAX_FETCH_CHARS]}


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None
