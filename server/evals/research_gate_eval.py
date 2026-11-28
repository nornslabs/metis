"""Run one Researcher gate case through the real gate (``research_input``).

Used by ``evals.run_gates``. A case freezes the idea, what is saved, the searches already run and
the KB's matches, so the item is built here exactly as the tool builds it, with the matches
included, and goes to ``run_gate`` with a judge on a real or recorded model. A code check rejects
repeats before any judge call. The outcome is ``run`` (the call passes) or ``refuse`` (rejected).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from langchain_core.messages import AIMessage, BaseMessage

from evals.gate_cases import ResearchGateCase
from metis.agent.gate import GateContext, GateDecisionKind, ModelJudge, run_gate
from metis.agent.tools.research_gates import RESEARCH_INPUT, RunKnowledge, gate_item
from metis.core.ports import LLMProvider, ToolDefinition

ITEM_MARKER = "\n\nItem:\n"
RUN, REFUSE = "run", "refuse"


def research_item(case: ResearchGateCase) -> dict[str, object]:
    """The item the tool builds for the gate, with the case's frozen KB matches."""
    knowledge = RunKnowledge(
        idea_title=case.idea.title,
        idea_text=case.idea.text,
        brief=case.brief,
        saved=case.saved,
        saved_urls=case.saved_urls,
    )
    item = gate_item(
        case.tool,
        case.target,
        knowledge,
        earlier_queries=case.earlier_queries,
        fetched_urls=case.fetched_urls,
    )
    return {**item, "kb_matches": [match.model_dump() for match in case.kb_matches]}


async def run_research_case_once(case: ResearchGateCase, model: LLMProvider) -> str:
    """``run`` or ``refuse`` for one case with a fresh gate context."""
    context = GateContext(judge=ModelJudge(model), budget=None, emit=lambda event: None)
    decision = await run_gate(RESEARCH_INPUT, case.tool, research_item(case), context)
    return RUN if decision.kind is GateDecisionKind.PASSED else REFUSE


class RecordedResearchChat:
    """A chat model that replays recorded judge verdicts, found by idea, tool and target."""

    def __init__(
        self, verdicts: Mapping[tuple[str, str], str], cases: Sequence[ResearchGateCase]
    ) -> None:
        self._verdicts = verdicts
        self._case_by_call = {(c.idea.title, c.tool, c.target): c.id for c in cases}

    def bind_tools(self, tools: Sequence[ToolDefinition]) -> RecordedResearchChat:
        return self

    async def ainvoke(self, messages: Sequence[BaseMessage], config: object = None) -> AIMessage:
        prompt = str(messages[-1].content)
        item = json.loads(prompt.split(ITEM_MARKER, 1)[1])
        case = self._case_by_call[(item["idea_title"], item["tool"], item["target"])]
        return AIMessage(content=self._verdicts[(case, "input")])

    async def aclose(self) -> None:
        return None
