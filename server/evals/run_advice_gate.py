"""``uv run python -m evals.run_advice_gate``: review the frozen suggestions with the Advisor gate.

Needs no database and no Redis (settings still load, so set the server's env, e.g. from
``.env``): each case goes through ``review_suggestion`` (the function ``save_suggestion`` uses)
with a judge on a real model. Set ``EVAL_LLM_BASE_URL``, ``EVAL_LLM_API_KEY`` and
``EVAL_LLM_MODEL`` (any OpenAI-compatible endpoint), or pass ``--recorded`` to replay the
verdicts in ``advice_gates/recorded.jsonl`` (offline, no key). A case a code check rejects needs
no verdict: the model is never called for it.

Exit code: 0 when the pass rate reaches ``--min-pass-rate``, 1 when it does not, 2 when the run
could not start (bad case file, missing settings).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage

from evals.advice_gate_cases import (
    CASES_PATH,
    RECORDED_PATH,
    AdviceGateCase,
    AdviceGateCaseFileError,
    load_advice_gate_cases,
)
from evals.run_gates import (
    DEFAULT_MIN_PASS_RATE,
    DEFAULT_REPEAT,
    EXIT_BELOW_THRESHOLD,
    EXIT_OK,
    EXIT_SETUP,
    ITEM_MARKER,
    CaseResult,
    SetupError,
    build_eval_model,
    format_report,
    pass_rate,
)
from metis.agent.gate import GateContext, GateDecisionKind, Judge, ModelJudge
from metis.agent.tools.advice_gate import (
    AdviceBrief,
    WeakParam,
    build_advice_gate,
    review_suggestion,
)
from metis.agent.tools.scoring import SourceBook
from metis.core.ports import LLMProvider, ToolDefinition

WRONG_CHECK = "wrong check"

__all__ = [
    "EXIT_BELOW_THRESHOLD",
    "EXIT_OK",
    "EXIT_SETUP",
    "RecordedChat",
    "evaluate",
    "load_verdicts",
    "main",
    "pass_rate",
]


class RecordedChat:
    """A chat model that replays recorded judge verdicts, found by the suggestion's title."""

    def __init__(self, verdicts: Mapping[str, str], case_by_title: Mapping[str, str]):
        self._verdicts = verdicts
        self._case_by_title = case_by_title

    def bind_tools(self, tools: Sequence[ToolDefinition]) -> RecordedChat:
        return self

    async def ainvoke(self, messages: Sequence[BaseMessage], config: object = None) -> AIMessage:
        prompt = str(messages[-1].content)
        item = json.loads(prompt.split(ITEM_MARKER, 1)[1])
        case = self._case_by_title[item["suggestion"]["title"]]
        return AIMessage(content=self._verdicts[case])

    async def aclose(self) -> None:
        return None


def load_verdicts(path: Path = RECORDED_PATH) -> dict[str, str]:
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return {row["case"]: row["verdict"] for row in lines}


class _CountingJudge:
    """A judge that counts its calls, to tell a code rejection from a judge rejection."""

    def __init__(self, inner: Judge) -> None:
        self._inner = inner
        self.calls = 0

    async def verdict(self, instruction: str, item: str) -> str | None:
        self.calls += 1
        return await self._inner.verdict(instruction, item)


async def run_case_once(case: AdviceGateCase, model: LLMProvider) -> str:
    """``pass``, ``reject``, or ``wrong check`` when the case is rejected by the other check.

    A ``code`` case must be rejected without a judge call; a ``judge`` case must reach the judge.
    """
    judge = _CountingJudge(ModelJudge(model))
    context = GateContext(judge=judge, budget=None, emit=lambda event: None)
    book = SourceBook()
    book.add(case.known_urls)
    brief = AdviceBrief(
        case.idea.title,
        case.idea.text,
        tuple(WeakParam(w.param, w.raw, w.reason) for w in case.weakest),
    )
    decision = await review_suggestion(
        context, build_advice_gate(book), brief, case.saved_titles, case.suggestion
    )
    if decision.kind is GateDecisionKind.PASSED:
        return "pass"
    return "reject" if (judge.calls > 0) == (case.reject_by == "judge") else WRONG_CHECK


async def evaluate(
    cases: Sequence[AdviceGateCase], model: LLMProvider, repeat: int
) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:
        got = tuple([await run_case_once(case, model) for _ in range(repeat)])
        results.append(CaseResult(case.id, case.expect, got))
    return results


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cases = _select(load_advice_gate_cases(CASES_PATH), args.cases)
        if args.repeat < 1:
            raise SetupError("--repeat must be at least 1")
        model, name = _resolve_model(args.recorded, cases)
        results = asyncio.run(evaluate(cases, model, args.repeat))
    except (AdviceGateCaseFileError, SetupError) as exc:
        print(f"error: {exc}", file=sys.stderr)  # noqa: T201
        return EXIT_SETUP
    print(format_report(results, model=name))  # noqa: T201
    if args.json:
        payload = {
            "model": name,
            "pass_rate": pass_rate(results),
            "cases": [
                {"id": r.case_id, "expect": r.expect, "got": list(r.got), "passed": r.passed}
                for r in results
            ],
        }
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return EXIT_OK if pass_rate(results) >= args.min_pass_rate else EXIT_BELOW_THRESHOLD


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals.run_advice_gate", description=__doc__)
    parser.add_argument("--cases", nargs="+", metavar="ID", help="only these case ids")
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT, help="runs per case")
    parser.add_argument("--min-pass-rate", type=float, default=DEFAULT_MIN_PASS_RATE)
    parser.add_argument("--json", type=Path, metavar="FILE", help="also write the results here")
    parser.add_argument(
        "--recorded",
        nargs="?",
        type=Path,
        const=RECORDED_PATH,
        metavar="FILE",
        help="replay recorded verdicts instead of calling a model",
    )
    return parser


def _select(cases: tuple[AdviceGateCase, ...], ids: list[str] | None) -> tuple[AdviceGateCase, ...]:
    if not ids:
        return cases
    unknown = sorted(set(ids) - {c.id for c in cases})
    if unknown:
        raise SetupError(f"unknown case id(s): {', '.join(unknown)}")
    return tuple(c for c in cases if c.id in ids)


def _resolve_model(
    recorded: Path | None, cases: Sequence[AdviceGateCase]
) -> tuple[LLMProvider, str]:
    if recorded is not None:
        by_title = {c.suggestion.title: c.id for c in cases}
        return RecordedChat(load_verdicts(recorded), by_title), "recorded replay"
    return build_eval_model()


if __name__ == "__main__":
    raise SystemExit(main())
