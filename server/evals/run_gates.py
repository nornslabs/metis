"""``uv run python -m evals.run_gates``: review the frozen questions with the Interviewer's gates.

Needs no database and no Redis (settings still load, so set the server's env, e.g. from
``.env``): each case goes through ``review_question`` (the function the
``ask_user`` tool uses) with a judge on a real model. Set ``EVAL_LLM_BASE_URL``,
``EVAL_LLM_API_KEY`` and ``EVAL_LLM_MODEL`` (any OpenAI-compatible endpoint), or pass
``--recorded`` to replay the verdicts in ``gates/recorded.jsonl`` (offline, no key).

Exit code: 0 when the pass rate reaches ``--min-pass-rate``, 1 when it does not, 2 when the run
could not start (bad case file, missing settings).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage

from evals.gate_cases import (
    CASES_PATH,
    RECORDED_PATH,
    GateCase,
    GateCaseFileError,
    load_gate_cases,
)
from metis.adapters.llm.chat import build_chat_model
from metis.agent.gate import GateContext, ModelJudge
from metis.agent.tools.interview_gates import (
    INPUT_INSTRUCTION,
    IdeaTexts,
    ReviewOutcome,
    review_question,
)
from metis.agent.tools.question_options import OptionArgs
from metis.core.ports import LLMProvider, ToolDefinition

DEFAULT_REPEAT = 2
DEFAULT_MIN_PASS_RATE = 0.9
CALL_TIMEOUT_SECONDS = 60.0
EXIT_OK, EXIT_BELOW_THRESHOLD, EXIT_SETUP = 0, 1, 2
ITEM_MARKER = "\n\nItem:\n"


class SetupError(Exception):
    """The run cannot start; the message says what to fix."""


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    expect: str
    got: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return all(outcome == self.expect for outcome in self.got)


class RecordedChat:
    """A chat model that replays recorded judge verdicts, found by question and gate."""

    def __init__(
        self, verdicts: Mapping[tuple[str, str], str], case_by_question: Mapping[str, str]
    ):
        self._verdicts = verdicts
        self._case_by_question = case_by_question

    def bind_tools(self, tools: Sequence[ToolDefinition]) -> RecordedChat:
        return self

    async def ainvoke(self, messages: Sequence[BaseMessage], config: object = None) -> AIMessage:
        prompt = str(messages[-1].content)
        item = json.loads(prompt.split(ITEM_MARKER, 1)[1])
        case = self._case_by_question[item["question"]]
        gate = "input" if INPUT_INSTRUCTION in prompt else "output"
        return AIMessage(content=self._verdicts[(case, gate)])

    async def aclose(self) -> None:
        return None


def load_verdicts(path: Path = RECORDED_PATH) -> dict[tuple[str, str], str]:
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return {(row["case"], row["gate"]): row["verdict"] for row in lines}


async def run_case_once(case: GateCase, model: LLMProvider) -> str:
    """The review outcome of one case with a fresh gate context, as its ``ReviewOutcome`` value."""
    context = GateContext(judge=ModelJudge(model), budget=None, emit=lambda event: None)
    idea = IdeaTexts(case.idea.title, case.idea.text, [(t.question, t.answer) for t in case.turns])
    options = [OptionArgs(**option.model_dump()) for option in case.options]
    review = await review_question(context, idea, case.question, options)
    return review.outcome.value


async def evaluate(cases: Sequence[GateCase], model: LLMProvider, repeat: int) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:
        got = tuple([await run_case_once(case, model) for _ in range(repeat)])
        results.append(CaseResult(case.id, ReviewOutcome(case.expect).value, got))
    return results


def pass_rate(results: Sequence[CaseResult]) -> float:
    return sum(r.passed for r in results) / len(results) if results else 0.0


def format_report(results: Sequence[CaseResult], *, model: str) -> str:
    width = max((len(r.case_id) for r in results), default=4)
    lines = [f"{'case':<{width}}  {'expect':<9}  {'got':<20}  result"]
    for r in results:
        verdict = "PASS" if r.passed else "FAIL"
        lines.append(f"{r.case_id:<{width}}  {r.expect:<9}  {' / '.join(r.got):<20}  {verdict}")
    failing = [r for r in results if not r.passed]
    if failing:
        lines += ["", "Failures:"]
        lines += [f"  {r.case_id}: expected {r.expect}, got {' / '.join(r.got)}" for r in failing]
    passed = sum(r.passed for r in results)
    lines += [
        "",
        f"Pass rate: {passed}/{len(results)} = {pass_rate(results):.0%}",
        f"Model: {model}",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cases = _select(load_gate_cases(CASES_PATH), args.cases)
        if args.repeat < 1:
            raise SetupError("--repeat must be at least 1")
        model, name = _resolve_model(args.recorded, cases)
        results = asyncio.run(evaluate(cases, model, args.repeat))
    except (GateCaseFileError, SetupError) as exc:
        print(f"error: {exc}", file=sys.stderr)  # noqa: T201
        return EXIT_SETUP
    print(format_report(results, model=name))  # noqa: T201
    if args.json:
        payload = {"model": name, "pass_rate": pass_rate(results), "cases": _as_json(results)}
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return EXIT_OK if pass_rate(results) >= args.min_pass_rate else EXIT_BELOW_THRESHOLD


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals.run_gates", description=__doc__)
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


def _select(cases: tuple[GateCase, ...], ids: list[str] | None) -> tuple[GateCase, ...]:
    if not ids:
        return cases
    unknown = sorted(set(ids) - {c.id for c in cases})
    if unknown:
        raise SetupError(f"unknown case id(s): {', '.join(unknown)}")
    return tuple(c for c in cases if c.id in ids)


def _resolve_model(recorded: Path | None, cases: Sequence[GateCase]) -> tuple[LLMProvider, str]:
    if recorded is not None:
        by_question = {c.question: c.id for c in cases}
        return RecordedChat(load_verdicts(recorded), by_question), "recorded replay"
    missing = [
        n
        for n in ("EVAL_LLM_BASE_URL", "EVAL_LLM_API_KEY", "EVAL_LLM_MODEL")
        if not os.environ.get(n)
    ]
    if missing:
        raise SetupError(f"set {', '.join(missing)} (or pass --recorded)")
    model = os.environ["EVAL_LLM_MODEL"]
    chat = build_chat_model(
        base_url=os.environ["EVAL_LLM_BASE_URL"],
        api_key=os.environ["EVAL_LLM_API_KEY"],
        model=model,
        purpose="gate",
        timeout_seconds=CALL_TIMEOUT_SECONDS,
        long_timeout_seconds=CALL_TIMEOUT_SECONDS,
    )
    return chat, model


def _as_json(results: Sequence[CaseResult]) -> list[dict[str, object]]:
    return [
        {"id": r.case_id, "expect": r.expect, "got": list(r.got), "passed": r.passed}
        for r in results
    ]


if __name__ == "__main__":
    raise SystemExit(main())
