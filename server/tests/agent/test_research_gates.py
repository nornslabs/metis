"""The Researcher's input gate on the Exa tools: what the model sees and what Exa is asked.

Seam: the gated tools the Researcher's loop receives (``with_research_gate`` over
``with_call_cap``), called as the loop calls them, with fake Exa tools, a fake judge, a fake
Redis and a fake knowledge loader. The tests check external behavior: whether Exa was called,
what the model was told, how many of the run's calls were spent, and the ``gate`` events.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel

from metis.agent.gate import GateContext, GateRefusal
from metis.agent.text_match import is_near_duplicate
from metis.agent.tools.exa import FETCH_TOOL, SEARCH_TOOL, ExaCallBudget, with_call_cap
from metis.agent.tools.research_gates import (
    CallMemory,
    RunKnowledge,
    normalised_url,
    with_kb_matches,
    with_research_gate,
)

LIMIT = "The web search limit is reached."
IDEA = RunKnowledge(
    idea_title="Invoice chase",
    idea_text="Polite, escalating payment reminders for freelancers.",
    brief="{}",
    saved=("competitor: Acme CRM",),
    saved_urls=("https://acme.example.com/pricing",),
)
SPECIFIC = "Acme CRM pricing for freelancers"
VAGUE = "competitors"
REASON = "Too vague: name a product or a segment."


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.sets: dict[str, set[bytes]] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def get(self, key: str) -> bytes | None:
        value = self.values.get(key)
        return None if value is None else str(value).encode()

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def sadd(self, key: str, value: str) -> None:
        self.sets.setdefault(key, set()).add(value.encode())

    async def smembers(self, key: str) -> set[bytes]:
        return set(self.sets.get(key, set()))


class FakeJudge:
    """Replies in order (the last reply repeats); records the item text it was shown."""

    def __init__(self, *replies: str | None | Exception) -> None:
        self._replies = list(replies) or [None]
        self.items: list[str] = []

    async def verdict(self, instruction: str, item: str) -> str | None:
        self.items.append(item)
        reply = self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


class SearchArgs(BaseModel):
    query: str
    objective: str = ""


class FetchArgs(BaseModel):
    url: str


class Harness:
    def __init__(self, judge: FakeJudge, *, limit: int = 12) -> None:
        self.redis = FakeRedis()
        self.run_id = uuid4()
        self.exa_calls: list[tuple[str, dict[str, Any]]] = []
        self.events: list[Mapping[str, Any]] = []
        self.judge = judge
        self.budget = ExaCallBudget(self.redis, self.run_id, limit)  # type: ignore[arg-type]
        self.context = GateContext(judge=judge, budget=None, emit=self.events.append)
        self.knowledge = IDEA
        self.fail_exa = False
        self.knowledge_loader: Any = None
        capped = with_call_cap(
            [self._exa(SEARCH_TOOL, SearchArgs), self._exa(FETCH_TOOL, FetchArgs)],
            self.budget,
            limit_message=LIMIT,
        )
        self.tools = {
            tool.name: tool
            for tool in with_research_gate(
                capped,
                budget=self.budget,
                memory=CallMemory(self.redis, self.run_id),  # type: ignore[arg-type]
                context=self.context,
                load_knowledge=self._load,
                limit_message=LIMIT,
            )
        }

    async def _load(self) -> RunKnowledge:
        if self.knowledge_loader is not None:
            return await self.knowledge_loader()
        return self.knowledge

    def _exa(self, name: str, schema: type[BaseModel]) -> BaseTool:
        async def call(**arguments: Any) -> str:
            if self.fail_exa:
                raise RuntimeError("exa down")
            self.exa_calls.append((name, arguments))
            return "hits"

        return StructuredTool.from_function(
            coroutine=call, name=name, description=name, args_schema=schema
        )

    async def search(self, query: str) -> Any:
        return await self.tools[SEARCH_TOOL].ainvoke({"query": query})

    async def fetch(self, url: str) -> Any:
        return await self.tools[FETCH_TOOL].ainvoke({"url": url})

    @property
    def decisions(self) -> list[tuple[str, str, str]]:
        return [(e["specialist"], e["gate"], e["decision"]) for e in self.events]

    async def spent(self) -> int:
        return self.redis.values.get(f"agent:exa:{self.run_id}:calls", 0)


async def test_a_specific_search_that_fills_a_gap_runs_and_spends_one_call() -> None:
    harness = Harness(FakeJudge(None))

    result = await harness.search(SPECIFIC)

    assert result == "hits"
    assert [name for name, _ in harness.exa_calls] == [SEARCH_TOOL]
    assert await harness.spent() == 1
    assert harness.decisions == [("researcher", "research_input", "passed")]


async def test_a_vague_search_makes_no_exa_call_spends_no_budget_and_gives_the_reason() -> None:
    harness = Harness(FakeJudge(REASON))

    with pytest.raises(GateRefusal, match="Too vague"):
        await harness.search(VAGUE)

    assert harness.exa_calls == []
    assert await harness.spent() == 0
    assert harness.decisions == [("researcher", "research_input", "retried")]


async def test_a_duplicate_search_is_refused_without_a_judge_call() -> None:
    harness = Harness(FakeJudge(None))
    await harness.search(SPECIFIC)
    shown = len(harness.judge.items)

    with pytest.raises(GateRefusal, match="similar search"):
        await harness.search("pricing for freelancers Acme CRM")

    assert len(harness.judge.items) == shown
    assert len(harness.exa_calls) == 1
    assert await harness.spent() == 1


async def test_a_page_already_fetched_is_refused_even_when_the_url_is_written_differently() -> None:
    harness = Harness(FakeJudge(None))
    await harness.fetch("https://docs.example.com/guide")

    with pytest.raises(GateRefusal, match="already fetched or saved"):
        await harness.fetch("https://www.docs.example.com/guide/?utm_source=x#top")

    assert [name for name, _ in harness.exa_calls] == [FETCH_TOOL]


async def test_a_page_already_saved_in_the_snapshot_is_refused() -> None:
    harness = Harness(FakeJudge(None))

    with pytest.raises(GateRefusal, match="already fetched or saved"):
        await harness.fetch("https://acme.example.com/pricing")

    assert harness.exa_calls == []


async def test_a_search_rejected_three_times_is_skipped_and_tells_the_model_to_go_on() -> None:
    harness = Harness(FakeJudge(REASON))

    for query in ("competitors", "market size"):
        with pytest.raises(GateRefusal):
            await harness.search(query)
    answer = await harness.search("trends")

    assert "was not made" in answer and "finish the research" in answer
    assert harness.exa_calls == []
    assert await harness.spent() == 0
    assert [d[2] for d in harness.decisions] == ["retried", "retried", "skipped"]


async def test_after_a_skip_the_next_rejected_search_is_skipped_at_once_until_one_passes() -> None:
    harness = Harness(FakeJudge(REASON, REASON, REASON, REASON, None, REASON))
    for query in ("competitors", "market size"):
        with pytest.raises(GateRefusal):
            await harness.search(query)
    await harness.search("trends")

    assert "was not made" in await harness.search("market")  # skipped, not refused again
    assert await harness.search(SPECIFIC) == "hits"  # a pass resets the count
    with pytest.raises(GateRefusal):
        await harness.search("pricing")


async def test_a_search_is_remembered_only_once_exa_has_answered() -> None:
    harness = Harness(FakeJudge(None))
    harness.fail_exa = True

    with pytest.raises(RuntimeError):
        await harness.search(SPECIFIC)
    harness.fail_exa = False

    assert await harness.search(SPECIFIC) == "hits"


async def test_an_unreadable_run_state_lets_the_call_through_unreviewed() -> None:
    harness = Harness(FakeJudge(REASON))

    async def broken() -> RunKnowledge:
        raise RuntimeError("no database")

    harness.knowledge_loader = broken

    assert await harness.search(VAGUE) == "hits"
    assert harness.events == []


async def test_search_and_fetch_keep_separate_retries() -> None:
    harness = Harness(FakeJudge(REASON))
    for query in ("competitors", "market size"):
        with pytest.raises(GateRefusal):
            await harness.search(query)

    with pytest.raises(GateRefusal):
        await harness.fetch("https://docs.example.com/a")


async def test_a_spent_budget_is_answered_before_the_gate() -> None:
    harness = Harness(FakeJudge(None), limit=1)
    await harness.search(SPECIFIC)
    harness.events.clear()
    shown = len(harness.judge.items)

    answer = await harness.search("something new about Beta Invoices")

    assert answer == LIMIT
    assert harness.events == []
    assert len(harness.judge.items) == shown
    assert len(harness.exa_calls) == 1


async def test_a_judge_error_lets_the_search_through() -> None:
    harness = Harness(FakeJudge(RuntimeError("model down")))

    assert await harness.search(VAGUE) == "hits"
    assert harness.decisions == [("researcher", "research_input", "passed")]


async def test_the_judge_sees_the_idea_what_is_saved_and_the_earlier_queries() -> None:
    harness = Harness(FakeJudge(None))
    await harness.search(SPECIFIC)

    await harness.search("Beta Invoices reviews")

    shown = json.loads(harness.judge.items[-1])
    assert shown["idea_title"] == "Invoice chase"
    assert shown["saved"] == ["competitor: Acme CRM"]
    assert shown["earlier_queries"] == [SPECIFIC]
    assert shown["target"] == "Beta Invoices reviews"


async def test_the_kb_matches_are_shown_to_the_judge_only_when_it_is_reached() -> None:
    looked_up: list[str] = []

    async def lookup(query: str) -> list[dict[str, Any]]:
        looked_up.append(query)
        return [{"name": "Acme CRM", "url": "https://acme.example.com"}]

    judge = FakeJudge(None)
    harness = Harness(judge)
    harness.context.judge = with_kb_matches(harness.context, lookup).judge

    await harness.search(SPECIFIC)
    with pytest.raises(GateRefusal):
        await harness.search(SPECIFIC)  # a code check rejects it: no judge, so no lookup

    assert looked_up == [SPECIFIC]
    assert json.loads(judge.items[0])["kb_matches"][0]["name"] == "Acme CRM"


async def test_a_failing_kb_lookup_lets_the_judge_decide_without_matches() -> None:
    async def lookup(query: str) -> list[dict[str, Any]]:
        raise RuntimeError("no database")

    judge = FakeJudge(None)
    harness = Harness(judge)
    harness.context.judge = with_kb_matches(harness.context, lookup).judge

    assert await harness.search(SPECIFIC) == "hits"
    assert "kb_matches" not in json.loads(judge.items[0])


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        ("https://Example.com/a/", "http://www.example.com/a#x", True),
        ("https://example.com/a?utm_source=n&id=1", "https://example.com/a?id=1", True),
        ("https://example.com/a?id=1", "https://example.com/a?id=2", False),
        ("https://example.com/a", "https://example.com/b", False),
    ],
)
def test_urls_match_without_scheme_www_fragment_slash_or_tracking(
    first: str, second: str, same: bool
) -> None:
    assert (normalised_url(first) == normalised_url(second)) is same


def test_queries_with_the_same_words_in_another_order_are_near_duplicates() -> None:
    assert is_near_duplicate("Acme CRM pricing", "pricing Acme CRM")
    assert not is_near_duplicate("Acme CRM pricing", "Beta invoices reviews")
    assert not is_near_duplicate("", "anything")
