# PRD: test-scoring-evals

Linear: SHIP-243 · https://linear.app/heimdallabs/issue/SHIP-243/27-scoring-eval-set

Milestone: M4 — Scoring and advice. Branch: `test/scoring-evals`. Blocked by SHIP-240 (`feat-scorer`, done) and SHIP-210 (`chore-ci-pipeline`, done).

## Problem / Goal

Scores must stay comparable over time, but nothing tells us when a prompt or model change moves them. The Scorer has unit and job tests with a scripted model; those prove the wiring, not the judgement. `code-standards.md` says "scoring changes must pass `evals/`", and no `evals/` exists.

Goal: a small, fixed eval set (12–15 ideas with frozen interview briefs and frozen research snapshots, no live Exa) and a runner, `uv run python -m evals.run_scoring`, that runs the real Scorer on each case with a configured model, checks the band, the per-parameter ranges and the evidence, runs each case twice to flag variance, and prints a table with a pass rate. A manual CI job runs it against a real model; a cheap offline CI job runs it with a recorded fake model to check the harness itself.

## User stories

1. As a developer changing `scorer.v2.md` (or adding v3), I want one command that scores a fixed set of ideas, so that I see what my change did to the verdicts.
2. As a developer, I want the run to print a table with one row per case (expected band, got band, total, per-parameter pass or fail), so that I can see which case moved and why.
3. As a developer, I want a pass rate and a band accuracy, so that I can compare two prompts or two models in one number.
4. As a developer, I want every failure listed with the reason (band mismatch, parameter out of range, missing evidence), so that I do not read raw model output to learn what broke.
5. As a developer, I want the cases to include clear build, promising and advise ideas, so that the three bands are all covered.
6. As a developer, I want each case to carry a frozen interview brief and a frozen research snapshot, so that results do not depend on Exa or on a prior model run.
7. As a developer, I want each case to give an expected band and an allowed range for the parameters that matter (for example `uniqueness: 2–4`), so that the check is firm where the idea is clear and loose where it is not.
8. As a developer, I want the harness to fail a case whose parameter has evidence not from that case's snapshot, or no evidence without `no_evidence`, so that the "no invented links" rule is checked on real model output.
9. As a developer, I want each case run twice and any parameter that differs by more than 1 point flagged, so that I know how noisy a verdict is.
10. As a developer, I want the model, endpoint and key to come from env, so that the same harness runs against any OpenAI-compatible model.
11. As a developer, I want no Exa call in the run, so that it is cheap, repeatable and needs no Exa key.
12. As a developer, I want a non-zero exit code when a case fails or the pass rate is under a threshold, so that CI can gate on it.
13. As a maintainer, I want a manual `workflow_dispatch` job that runs the evals with an LLM key secret, so that a prompt change can be checked on GitHub before M4 is closed.
14. As a maintainer, I want an offline job on every pull request that runs the harness with a recorded fake model, so that a harness bug is caught without a key or a spend.
15. As a maintainer, I want the offline job to prove the harness can fail (a recorded bad answer is reported as a failure), so that a harness that always passes does not go unnoticed.
16. As a developer, I want a short document on how to add a case and how to read the table, so that the set grows without guessing.
17. As a developer, I want the Scorer run through the same code path as a real run, so that an eval cannot pass on a path production does not take.
18. As a developer, I want the eval data left out of a real workspace (a throwaway workspace, removed after the run), so that evals never touch user data.
19. As a maintainer, I want case files validated on load (known band, params from the rubric, ranges 0–10, brief and snapshot shape), so that a typo in a case fails fast, not as a mystery score.

## Requirements

1. **Cases** (`server/evals/scoring/cases.jsonl`): 14 cases, one JSON object per line: `id`, `title`, `description`, `brief` (the frozen `InterviewBrief` shape), `answers` (the user's interview answers), `snapshot` (summary, items with url / quote / claim / confidence, competitors with url / overlap / pricing, market facts), `expect`: `{band, total?: [min, max], params: {<param>: [min, max]}}`. Spread: 5 `build`, 5 `promising`, 4 `advise`; at least one case with thin research (low confidence, a gap marked `no_evidence`) and one with no snapshot items.
2. **Loader** (`evals/cases.py`): reads and validates every line against a Pydantic model; unknown parameter names, ranges outside 0–10 or min above max, an unknown band, or a duplicate `id` stop the run before any model call.
3. **Runner** (`evals/run_scoring.py`, `python -m evals.run_scoring`): options `--cases` (filter by id), `--repeat` (default 2), `--min-pass-rate` (default 0.8), `--json` (write results). Exit code 1 when any check fails and the pass rate is below the threshold, 2 on a setup error.
4. **Seam**: one. Per case, the runner seeds a throwaway workspace (idea at stage `scoring`, interview brief and answers, a closed research snapshot with items and competitors) in the configured Postgres, queues a run, and calls the `run_graph` job through the production wiring, with the real `LLMGateway` and the real Scorer node (not a copy). Exa is not configured for the eval workspace, so the Scorer runs with no search tool (it scores from the snapshot, as in the "no Exa key" path). The score run the job stores is read back through `scoring.latest_score`. The workspace is removed after each case.
5. **Model**: env `EVAL_LLM_BASE_URL`, `EVAL_LLM_API_KEY`, `EVAL_LLM_MODEL` become the eval workspace's tested LLM key and score-purpose model. Temperature stays the Scorer's own `0.0`. The eval does not set a seed (the gateway and the `LLMProvider` port have none; see Out of scope).
6. **Checks per run** (pure functions in `evals/checks.py`): (a) band equals `expect.band`; (b) every parameter named in `expect.params` has `raw` in range; (c) every parameter has a reason, a confidence, and either evidence whose URLs are all in the case's snapshot (compared with the Scorer's `normalize_url`) or `no_evidence=true`; (d) the total is inside `expect.total` when given. A run that ends without a stored score (run `failed`) is a failed case with the error code.
7. **Variance**: each case runs `--repeat` times (default 2) as separate runs. A parameter whose `raw` differs by more than 1 between the runs is flagged `unstable`; a changed band is flagged too. A case passes when every run passes; flags are reported, and do not fail the case on their own.
8. **Report** (`evals/report.py`): a table (id, expected band, got band per run, total per run, failed checks, flags), then lines: pass rate (cases passed / cases), band accuracy (runs with the right band / runs), unstable count, token usage and cost from `ideas.llm_usage`, and the prompt name and model. Plain text, no colour codes in CI.
9. **Offline mode**: `--recorded <file>` swaps the model for a replay of recorded tool-call replies (`server/evals/scoring/recorded.jsonl`, one entry per case and repeat: the `submit_scores` arguments), built on the existing scripted-LLM idea. The record includes at least one deliberately wrong answer (wrong band, out-of-range parameter, evidence URL not in the snapshot) so the harness is seen to report failures. The offline job asserts the expected set of failures, not a clean pass.
10. **CI** (`.github/workflows/evals.yml`): job `harness` on `pull_request` (path filter `server/evals/**`, `server/metis/agent/**`, `server/metis/prompts/**`) with Postgres and Redis services as in `ci.yml`, running `--recorded` and checking the failures match; job `scoring` on `workflow_dispatch` only, inputs for the model, secrets `EVAL_LLM_API_KEY` and `EVAL_LLM_BASE_URL`, running the real model, uploading the `--json` result as an artifact.
11. **Docs** (`server/evals/README.md` and a link from the root `README.md`): how to run locally (env, Postgres and Redis), how to read the table, how to add a case (fields, how to pick ranges, how to freeze a snapshot), how to refresh `recorded.jsonl`.
12. **Cleanup**: remove the empty `server/metis/evals/` folder and its `.gitkeep`; sync the folder tree in `AGENTS.md` and `architecture.md` (see Open questions).

## Out of scope

- Evals for other specialists (Interviewer, Researcher, Advisor), calibration, and tuning the prompt to reach the pass rate (a separate change if the first real run is under 80%).
- A seed parameter: needs a change to the `LLMProvider` port; the issue says "when supported", and it is not.
- Live Exa calls, and live research snapshots.
- Any `web/` change, API route, migration or change to the Scorer's behaviour.
- Scheduled runs and result history over time.

## Touches

- `server/evals/` (new): `scoring/cases.jsonl`, `scoring/recorded.jsonl`, `cases.py`, `checks.py`, `seed.py`, `run_scoring.py`, `report.py`, `recorded_llm.py`, `README.md`.
- `server/tests/evals/` (new): tests for the loader, checks, report and the offline run.
- `.github/workflows/evals.yml` (new), `README.md`.
- `server/pyproject.toml` (`evals` in the type-check and lint scope, import-linter if needed).
- `.agents/ctx/architecture.md`, `.agents/ctx/code-standards.md`, `AGENTS.md` (folder tree), `.agents/progress-tracker.md`.
- Reads `ideas`, `research`, `scoring`, `identity` through their `__init__.py` only; `metis` never imports `evals`.

## Dependencies

- `feat-scorer` (SHIP-240): done.
- `chore-ci-pipeline` (SHIP-210): done.

## Testing

Seam: one, the same as `tests/agent/test_scorer.py`: the `run_graph` job on real Postgres as `metis_app` and real Redis, with a scripted model. The eval harness drives that seam, so its own tests run the harness end to end offline (`--recorded`) and check what a developer sees: the exit code, the table, the pass rate, the failures listed, the flags.

A good test checks external behaviour (what is printed, the exit code, what is stored), not the harness's internals.

- Loader: a valid file loads; each kind of bad case (unknown param, range outside 0–10, min above max, duplicate id, unknown band) is refused with the line number.
- Checks (pure): band, range, evidence-in-snapshot, `no_evidence` rules, total range; one test per failure kind.
- Offline run on the committed cases with `recorded.jsonl`: exit code, the exact set of failing case ids, pass rate and band accuracy as printed.
- Variance: two recorded runs with a parameter 2 apart are flagged `unstable`; 1 apart is not.
- A run that fails (`score.invalid_submission`) is a failed case with its code, and the run goes on to the next case.
- The throwaway workspace is gone after the run.
- `uv run ruff check`, `uv run mypy`, `uv run lint-imports` pass locally; `uv run pytest` runs in CI.
- Not tested in CI: a real model (manual job only). The 80% band accuracy is measured by one manual run, and its result is recorded in the tracker.

Prior art: `tests/agent/test_scorer.py`, `tests/agent/score_helpers.py`, `tests/agent/interview_helpers.py` (`ScriptedLLM`), `tests/agent/run_job_helpers.py` (`job_ctx`, `run_job`).

## Acceptance criteria

- [ ] `cases.jsonl` has 12–15 validated cases covering `build`, `promising` and `advise`, with frozen briefs and snapshots.
- [ ] `uv run python -m evals.run_scoring` prints the table, the pass rate, the band accuracy and every failure.
- [ ] Each case runs twice; a parameter differing by more than 1 point is flagged.
- [ ] A case fails on a wrong band, a parameter out of range, or evidence not from its snapshot.
- [ ] No Exa call is made.
- [ ] The offline job passes in CI and fails if the harness stops reporting the recorded bad answers.
- [ ] The manual job runs against a real model and uploads its result.
- [ ] Band accuracy ≥ 80% on the current prompt, measured by one manual run (recorded in the tracker) before M4 is closed.
- [ ] How to add a case and how to read the results are documented.
- [ ] `ruff`, `mypy`, `lint-imports` pass; tests are added and run in CI.

## Open questions

None open.

## Resolved

- Evals live in `server/evals/`; the empty `server/metis/evals/` folder is deleted and the `AGENTS.md` tree is fixed (user, 2026-11-20).
- The runner uses Postgres and Redis: a throwaway workspace per case, the real Scorer through `run_graph`, no copy of the storage path (user, 2026-11-20).
- The manual job fails when the pass rate is under 80% (`--min-pass-rate 0.8`); variance flags never fail it (user, 2026-11-20).
- No seed: temperature 0 and the twice-run variance flag only; a seed needs an `LLMProvider` port change (user, 2026-11-20).

## Status

done
