"""The Researcher's input gate: is this Exa call worth one of the run's calls?

``research_input`` is a ``Gate`` over the shared framework in ``metis.agent.gate``. Every
``web_search_exa`` and ``web_fetch_exa`` call passes it before the call cap, so a refused or
skipped call makes no Exa call and spends no budget. Code checks come first (the same search or
the same page was not already used in this run); then the judge decides whether the topic is
specific, fills a gap in what the run has saved, and is not already answered by the competitor KB.

A spent call budget is answered before the gate with the cap message (no gate event, no judge
call): retrying cannot bring a call back. A rejection comes back to the model as a refusal
(``GateRefusal``); after the framework's retries the call is skipped and the Researcher goes on
with what it has. Nothing here raises into the run or sets ``last_error``.

The KB matches are looked up only when the judge is called (``KbJudge``), so a call a code check
rejects costs no embedding.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool
from redis.asyncio import Redis

from metis.agent.gate import Gate, GateContext, GateDecisionKind, Judge, enforce_gate
from metis.agent.text_match import is_near_duplicate
from metis.agent.tools.exa import (
    CACHE_TTL_SECONDS,
    FETCH_TOOL,
    SEARCH_TOOL,
    ExaCallBudget,
)
from metis.agent.tools.research_kb import ResearchScope, find_kb_matches, open_run_snapshot
from metis.core.logging import get_logger
from metis.modules import ideas, research

SPECIALIST = "researcher"
GATE_NAME = "research_input"
MAX_KB_MATCHES = 3
MAX_SAVED_LINES = 40
MAX_LINE_CHARS = 200
MAX_KB_QUERY_CHARS = 200
TRACKING_PARAMS = frozenset({"fbclid", "gclid", "ref", "ref_src"})
FINISH_HINT = "Go on with what you have: save what you found, then finish the research."

logger = get_logger(__name__)

INSTRUCTION = """\
The item is a call the Researcher wants to make to the web (`web_search_exa` with a query, or \
`web_fetch_exa` with a URL), with the idea, its brief, what the run has already saved, the \
queries and URLs it has already used, and the competitor KB's matches for the call.
Reject the call when any of these is true:
1. A search is not specific: it is a bare category such as "competitors" or "market size" and \
names no product, company, customer segment or claim.
2. It does not fill a gap: what is already saved answers it, or it has nothing to do with this \
idea.
3. The KB matches already answer it (for example it only looks for a competitor the KB already \
holds).
4. A fetch would add nothing to what is saved, or its URL is not a source for a gap.
Otherwise pass it."""


@dataclass(frozen=True)
class RunKnowledge:
    """What the gate reads about the run: the idea, its brief, and what is already saved."""

    idea_title: str
    idea_text: str
    brief: str
    saved: tuple[str, ...] = ()
    saved_urls: tuple[str, ...] = ()


KnowledgeLoader = Callable[[], Awaitable[RunKnowledge]]
KbLookup = Callable[[str], Awaitable[list[dict[str, Any]]]]


class CallMemory:
    """The searches and pages a run has used, in Redis, so a crash re-run shares them."""

    def __init__(self, redis: Redis, run_id: UUID) -> None:
        self._redis = redis
        self._keys = {
            SEARCH_TOOL: f"agent:exa:{run_id}:queries",
            FETCH_TOOL: f"agent:exa:{run_id}:urls",
        }

    async def recall(self, tool: str) -> list[str]:
        members = await self._redis.smembers(self._keys[tool])  # type: ignore[misc]
        return sorted(m.decode() if isinstance(m, bytes) else str(m) for m in members)

    async def remember(self, tool: str, value: str) -> None:
        await self._redis.sadd(self._keys[tool], value)  # type: ignore[misc]
        await self._redis.expire(self._keys[tool], CACHE_TTL_SECONDS)


def normalised_url(url: str) -> str:
    """``url`` without scheme, ``www.``, fragment, trailing slash or tracking parameters."""
    parts = urlsplit(url.strip())
    host = parts.netloc.casefold().removeprefix("www.")
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query)
        if not key.startswith("utm_") and key not in TRACKING_PARAMS
    )
    path = parts.path.rstrip("/")
    return f"{host}{path}" + (f"?{urlencode(query)}" if query else "")


def _duplicate_search(item: Any) -> str | None:
    if item["tool"] != SEARCH_TOOL:
        return None
    for earlier in item["earlier_queries"]:
        if is_near_duplicate(item["target"], earlier):
            return f'You already ran a similar search: "{earlier}". Search for something new.'
    return None


def _duplicate_fetch(item: Any) -> str | None:
    if item["tool"] != FETCH_TOOL:
        return None
    wanted = normalised_url(item["target"])
    if any(normalised_url(url) == wanted for url in item["known_urls"]):
        return "This page was already fetched or saved in this run. Fetch a page you have not read."
    return None


RESEARCH_INPUT = Gate(
    name=GATE_NAME,
    specialist=SPECIALIST,
    checks=(_duplicate_search, _duplicate_fetch),
    judge_instruction=INSTRUCTION,
)


class KbJudge:
    """A judge that adds the KB's matches for the call to the item before it decides.

    The lookup runs only when the judge is reached (after the code checks and the judge cap), and
    a failing lookup lets the judge decide without matches.
    """

    def __init__(self, inner: Judge, lookup: KbLookup) -> None:
        self._inner = inner
        self._lookup = lookup

    async def verdict(self, instruction: str, item: str) -> str | None:
        return await self._inner.verdict(instruction, await self._with_matches(item))

    async def _with_matches(self, item: str) -> str:
        try:
            data = json.loads(item)
            data["kb_matches"] = await self._lookup(data["target"])
            return json.dumps(data, ensure_ascii=False)
        except Exception:  # noqa: BLE001  (the judge goes on without matches)
            logger.warning("research_gate.kb_lookup_failed", exc_info=True)
            return item


def with_kb_matches(context: GateContext, lookup: KbLookup) -> GateContext:
    """``context`` with a judge that sees the KB matches (no judge stays no judge)."""
    if context.judge is None:
        return context
    return replace(context, judge=KbJudge(context.judge, lookup))


def with_research_gate(  # noqa: PLR0913  (each collaborator is a seam the tests replace)
    tools: Sequence[BaseTool],
    *,
    budget: ExaCallBudget,
    memory: CallMemory,
    context: GateContext,
    load_knowledge: KnowledgeLoader,
    limit_message: str,
) -> list[BaseTool]:
    """``tools`` (the capped Exa tools) behind the ``research_input`` gate."""

    def gated(tool: BaseTool) -> BaseTool:
        async def invoke(**arguments: Any) -> Any:
            if await _budget_spent(budget):
                return limit_message
            target = _target(tool.name, arguments)
            item = await _safe_item(tool.name, target, memory, load_knowledge)
            if item is not None:
                decision = await enforce_gate(RESEARCH_INPUT, tool.name, item, context)
                if decision.kind is GateDecisionKind.SKIPPED:
                    return f"The {_noun(tool.name)} was not made: {decision.reason} {FINISH_HINT}"
                context.attempts.pop((GATE_NAME, tool.name), None)
            result = await tool.ainvoke(arguments)
            await _remember(memory, tool.name, target)
            return result

        return StructuredTool.from_function(
            coroutine=invoke,
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
        )

    return [gated(tool) for tool in tools]


async def load_run_knowledge(scope: ResearchScope) -> RunKnowledge:
    """The idea, its brief and the run's saved findings, read in one short transaction."""
    async with scope.session() as session:
        idea = await ideas.get_idea(session, scope.workspace_id, scope.idea_id)
        brief = await ideas.get_interview_brief(session, scope.workspace_id, scope.idea_id)
        snapshot = await open_run_snapshot(session, scope)
        saved = await research.get_snapshot(session, scope.workspace_id, snapshot.id)
    lines = [f"competitor: {c.name}" for c in saved.competitors]
    lines += [f"{i.kind.value}: {i.title}: {i.claim}" for i in saved.items]
    urls = [c.url for c in saved.competitors]
    urls += [i.url for i in saved.items if i.url]
    return RunKnowledge(
        idea_title=idea.title,
        idea_text=idea.raw_text,
        brief=brief.model_dump_json() if brief is not None else "none",
        saved=tuple(line[:MAX_LINE_CHARS] for line in lines[:MAX_SAVED_LINES]),
        saved_urls=tuple(urls),
    )


def kb_lookup_for(scope: ResearchScope) -> KbLookup:
    """The KB read the judge sees: the top matches as small records."""

    async def lookup(query: str) -> list[dict[str, Any]]:
        matches = await find_kb_matches(scope, query[:MAX_KB_QUERY_CHARS], MAX_KB_MATCHES)
        return [
            {
                "name": m.competitor.name,
                "url": m.competitor.url,
                "description": m.competitor.description,
                "pricing": m.competitor.pricing,
            }
            for m in matches
        ]

    return lookup


def _target(tool_name: str, arguments: dict[str, Any]) -> str:
    key = "query" if tool_name == SEARCH_TOOL else "url"
    return str(arguments.get(key, "")).strip()


def _noun(tool_name: str) -> str:
    return "search" if tool_name == SEARCH_TOOL else "fetch"


def gate_item(
    tool_name: str,
    target: str,
    knowledge: RunKnowledge,
    *,
    earlier_queries: Sequence[str],
    fetched_urls: Sequence[str],
) -> dict[str, Any]:
    """The item the gate reviews; the tool and the gate evals both build it here."""
    return {
        "tool": tool_name,
        "target": target,
        "idea_title": knowledge.idea_title,
        "idea_text": knowledge.idea_text,
        "brief": knowledge.brief,
        "saved": list(knowledge.saved),
        "earlier_queries": list(earlier_queries),
        "known_urls": [*fetched_urls, *knowledge.saved_urls],
    }


async def _safe_item(
    tool_name: str, target: str, memory: CallMemory, load_knowledge: KnowledgeLoader
) -> dict[str, Any] | None:
    """The gate item, or ``None`` when the run's state cannot be read: a gate never fails a run."""
    try:
        return gate_item(
            tool_name,
            target,
            await load_knowledge(),
            earlier_queries=await memory.recall(SEARCH_TOOL),
            fetched_urls=await memory.recall(FETCH_TOOL),
        )
    except Exception:  # noqa: BLE001  (an unreadable state lets the call through, unreviewed)
        logger.warning("research_gate.state_unreadable", exc_info=True)
        return None


async def _budget_spent(budget: ExaCallBudget) -> bool:
    try:
        return await budget.exhausted()
    except Exception:  # noqa: BLE001  (the call cap still counts the call itself)
        logger.warning("research_gate.budget_unreadable", exc_info=True)
        return False


async def _remember(memory: CallMemory, tool_name: str, target: str) -> None:
    try:
        await memory.remember(tool_name, target)
    except Exception:  # noqa: BLE001  (losing a memory only lets a repeat through)
        logger.warning("research_gate.memory_failed", exc_info=True)
