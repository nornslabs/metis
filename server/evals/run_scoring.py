"""``uv run python -m evals.run_scoring``: score the eval cases and print how the Scorer did.

Needs Postgres (migrated, owner ``DATABASE_URL``) and Redis, like the server. With a real model
set ``EVAL_LLM_BASE_URL``, ``EVAL_LLM_API_KEY`` and ``EVAL_LLM_MODEL`` (any OpenAI-compatible
endpoint). ``--recorded`` replaces the model with the replay in ``scoring/recorded.jsonl``.

Exit code: 0 when the pass rate reaches ``--min-pass-rate``, 1 when it does not, 2 when the run
could not start (bad case file, missing settings).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from redis.asyncio import Redis
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from evals.cases import CASES_PATH, Case, CaseFileError, load_cases
from evals.checks import unstable_flags
from evals.harness import CaseRun, Harness, ModelClient, run_case_once
from evals.recorded_llm import RECORDED_PATH, RecordedLLM, load_recordings
from evals.report import (
    CaseOutcome,
    Usage,
    combine_usage,
    format_report,
    pass_rate,
    results_as_json,
)
from evals.seed import LlmConfig
from metis.agent.checkpoint import setup_checkpointer
from metis.agent.prompts import PROMPTS_DIR
from metis.core.config import get_settings

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_REPEAT = 2
DEFAULT_MIN_PASS_RATE = 0.8
APP_ROLE = "metis_app"
PLACEHOLDER_LLM = LlmConfig(
    base_url="https://recorded.eval.invalid/v1", api_key="recorded-eval-key", model="recorded"
)
EXIT_OK, EXIT_BELOW_THRESHOLD, EXIT_SETUP = 0, 1, 2


class SetupError(Exception):
    """The run cannot start; the message says what to fix."""


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cases = _select(load_cases(CASES_PATH), args.cases)
        return asyncio.run(_run(cases, args))
    except (CaseFileError, SetupError) as exc:
        print(f"error: {exc}", file=sys.stderr)  # noqa: T201
        return EXIT_SETUP


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals.run_scoring", description=__doc__)
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
        help="replay recorded answers instead of calling a model",
    )
    return parser


def _select(cases: tuple[Case, ...], ids: list[str] | None) -> tuple[Case, ...]:
    if not ids:
        return cases
    unknown = sorted(set(ids) - {c.id for c in cases})
    if unknown:
        raise SetupError(f"unknown case id(s): {', '.join(unknown)}")
    return tuple(c for c in cases if c.id in ids)


async def _run(cases: tuple[Case, ...], args: argparse.Namespace) -> int:
    if args.repeat < 1:
        raise SetupError("--repeat must be at least 1")
    settings = get_settings()
    app_url = _app_database_url(settings.database_url)
    owner = create_async_engine(settings.database_url)
    app = create_async_engine(app_url)
    redis = Redis.from_url(settings.redis_url)
    try:
        llm, client = _resolve_llm(args.recorded, cases)
        await setup_checkpointer(app_url)
        harness = Harness(
            owner=owner,
            sessions=async_sessionmaker(app, expire_on_commit=False),
            app_database_url=app_url,
            redis=redis,
            llm=llm,
            model_client=client,
        )
        outcomes, usage = await _evaluate(harness, cases, args.repeat)
    finally:
        await redis.aclose()
        await app.dispose()
        await owner.dispose()
    model = "recorded replay" if args.recorded else llm.model
    print(format_report(outcomes, model=model, prompt=_latest_prompt(), usage=usage))  # noqa: T201
    if args.json:
        args.json.write_text(
            json.dumps(results_as_json(outcomes, model=model, prompt=_latest_prompt()), indent=2),
            encoding="utf-8",
        )
    return EXIT_OK if pass_rate(outcomes) >= args.min_pass_rate else EXIT_BELOW_THRESHOLD


async def _evaluate(
    harness: Harness, cases: tuple[Case, ...], repeat: int
) -> tuple[list[CaseOutcome], Usage]:
    results = [await _evaluate_case(harness, case, repeat) for case in cases]
    return [outcome for outcome, _ in results], combine_usage([usage for _, usage in results])


async def _evaluate_case(harness: Harness, case: Case, repeat: int) -> tuple[CaseOutcome, Usage]:
    runs: list[CaseRun] = [await run_case_once(harness, case) for _ in range(repeat)]
    flags = unstable_flags([r.score for r in runs if r.score is not None])
    outcome = CaseOutcome(case.id, case.expect.band, tuple(r.outcome for r in runs), flags)
    return outcome, combine_usage([r.usage for r in runs])


def _resolve_llm(
    recorded: Path | None, cases: tuple[Case, ...]
) -> tuple[LlmConfig, ModelClient | None]:
    if recorded is not None:
        replay = RecordedLLM(load_recordings(recorded), {c.title: c.id for c in cases})
        return PLACEHOLDER_LLM, replay.client
    missing = [
        n
        for n in ("EVAL_LLM_BASE_URL", "EVAL_LLM_API_KEY", "EVAL_LLM_MODEL")
        if not os.environ.get(n)
    ]
    if missing:
        raise SetupError(f"set {', '.join(missing)} (or pass --recorded)")
    config = LlmConfig(
        os.environ["EVAL_LLM_BASE_URL"],
        os.environ["EVAL_LLM_API_KEY"],
        os.environ["EVAL_LLM_MODEL"],
    )
    return config, None


def _app_database_url(owner_url: str) -> str:
    password = os.environ.get("APP_DB_PASSWORD", APP_ROLE)
    return (
        make_url(owner_url)
        .set(username=APP_ROLE, password=password)
        .render_as_string(hide_password=False)
    )


def _latest_prompt() -> str:
    versions = sorted(PROMPTS_DIR.glob("scorer.v*.md"), key=lambda p: int(p.stem.split(".v")[1]))
    return versions[-1].name if versions else "scorer (no prompt file)"


if __name__ == "__main__":
    raise SystemExit(main())
