# Scoring evals

A fixed set of 14 ideas that the real Scorer scores, to catch regressions when a prompt or a
model changes. Scores must stay comparable over time; this is how we notice when they do not.

Each case freezes everything the Scorer reads (idea text, interview brief and answers, research
snapshot), so a run needs no Exa key and makes no search call. The Scorer, its tools and the
`scoring` module are the production ones; every other specialist is a stub.

## Run it

You need a migrated Postgres (`alembic upgrade head`, owner `DATABASE_URL`), Redis, and the same
env the server needs (`.env`). The runner creates a throwaway workspace per run and deletes it
afterwards. `DATABASE_URL` must be the owner (a superuser, as in CI and compose's `migrate`), not
`metis_app`: seeding writes tenant tables directly. The model endpoint must be `https` unless
the server runs with `ENVIRONMENT=development`.

```bash
cd server
export EVAL_LLM_BASE_URL=https://api.example.com/v1   # any OpenAI-compatible endpoint
export EVAL_LLM_API_KEY=...
export EVAL_LLM_MODEL=...
uv run python -m evals.run_scoring
```

| Option                | Default | What it does                                                |
| --------------------- | ------- | ----------------------------------------------------------- |
| `--cases ID [ID ...]` | all     | Run only these cases                                        |
| `--repeat N`          | 2       | Runs per case (separate runs, to measure variance)          |
| `--min-pass-rate X`   | 0.8     | Exit 1 when the pass rate is lower                          |
| `--json FILE`         | none    | Also write the results as JSON                              |
| `--recorded [FILE]`   | off     | Replay recorded answers instead of calling a model (offline) |

Exit code: `0` pass rate reached, `1` below `--min-pass-rate`, `2` the run could not start.

Temperature is the Scorer's own `0.0`. The gateway has no seed setting, so repeated runs can
differ; that is what the twice-run check measures.

## Read the results

```text
case             expect     got                     total      result
invoice-chase    build      build / build           79 / 79    PASS
habit-pets       promising  build / promising       79 / 56    FAIL (unstable)

Failures:
  habit-pets: run 1: band build, expected promising
Unstable:
  habit-pets: uniqueness unstable (5-8)

Pass rate: 13/14 = 93%
Band accuracy: 96%
```

- **Failures** make a case fail (any one run failing fails the case):
  - the band is not the expected one;
  - the total is outside `expect.total`;
  - a mark is outside its `expect.params` range;
  - a mark has no reason;
  - a mark has no evidence and does not say `no_evidence`, or says it and is confident;
  - a cited URL is not a source of the case's snapshot (checked after trimming a trailing `/`
    and a `#fragment`);
  - the run stored no score (the error code is shown, for example `score.invalid_submission`).
- **Unstable** is a report, not a failure: a band that changed between runs, or a mark that moved
  by more than 1 point.
- **Pass rate** is cases passed over cases. **Band accuracy** is runs with the right band over
  all runs. The target before M4 closes is a band accuracy of at least 80%.

## Add a case

Append one JSON object (one line) to `scoring/cases.jsonl`. The loader checks it and names the
line of any mistake.

| Field        | Meaning                                                                                  |
| ------------ | ---------------------------------------------------------------------------------------- |
| `id`         | Short kebab-case name, unique                                                            |
| `title`      | Idea title, unique (the Scorer sees it)                                                  |
| `idea_text`  | What the user typed                                                                      |
| `brief`      | Interview brief: `problem`, `target_customer`, `current_alternatives`, `willingness_to_pay`, `feasibility` (each text or `null`) |
| `answers`    | The user's interview answers: `{topic, question, answer}`                                |
| `snapshot`   | Frozen research: `summary`, `items` (`kind`, `title`, `url`, `quote`, `claim`, `confidence`) and `competitors` (`name`, `url`, `description`, `pricing`, `overlap`); `null` for no research |
| `expect`     | `band`, optional `total: [min, max]` inside the band, and `params: {name: [min, max]}`   |

Guidance:

1. Freeze the research by hand or copy a real snapshot. Competitor and market-fact items need a
   URL. Use `example` domains, not real sites.
2. Give `expect.params` only for marks you are firm about (the clearest one to three). Leave the
   rest out so a reasonable model is not failed on a judgement call. Anchors are in the written
   scale (`server-context.md`): a 2 is weak, 5 is middling, 8 is strong.
3. The band follows the total: `build` from 75, `promising` from 55, else `advise`.
4. Keep the spread: the set needs clear build, promising and advise cases, one with thin
   research and one with none.
5. Add the case's recorded answers to `scoring/recorded.jsonl` (below), then run
   `uv run python -m evals.run_scoring --recorded` and `uv run pytest tests/evals`.

## Recorded answers (offline check)

`scoring/recorded.jsonl` holds, per case and run, the `submit_scores` arguments a model would
send: `{"case": id, "run": 1, "params": [...]}`. `--recorded` replays them instead of calling a
model, so CI can check the harness without a key. The set holds a few deliberately bad answers:

| Case                    | Recorded problem                                    | Shows                       |
| ----------------------- | --------------------------------------------------- | --------------------------- |
| `habit-pets`            | run 1: marks that give the wrong band               | band and range failures     |
| `recipe-cost-calc`      | run 1: an evidence URL not in the snapshot (twice)  | refused submission, failed run |
| `pet-vaccine-reminders` | run 2: a mark outside its range                     | range failure               |
| `meeting-notes-sales`   | timing 9 then 7                                     | an unstable mark that passes |

`tests/evals/test_offline_run.py` asserts that exactly these cases fail, so the offline job also
catches a harness that stops reporting failures. If you change a case or the recording, update
the expected failures there. The offline run passes 11 of 14 cases (79%) on purpose.

## CI

`.github/workflows/evals.yml`:

- `harness` (pull requests that touch `server/evals/`, `server/metis/agent/` or the prompts):
  runs `tests/evals` and the recorded run. No key needed.
- `scoring` (manual, Actions > Evals > Run workflow): the real model. Needs the repository
  secrets `EVAL_LLM_BASE_URL` and `EVAL_LLM_API_KEY`; the model name is a run input. It fails
  under the minimum pass rate and uploads `results.json`.

## Gate evals

A second, smaller set checks the Interviewer's gates (SHIP-416): `evals/gates/cases.jsonl` freezes
14 candidate questions on three ideas. A *good* question must pass, a *generic* one ("What is the
pain?") and a *duplicate* of an earlier question must be rejected, and an *inferable* question
(its answer is in the idea text or an earlier answer) must be skipped with the quoted source.
No database or Redis is needed, only the server's env (the settings load).

```bash
cd server
uv run python -m evals.run_gates --recorded            # offline replay of gates/recorded.jsonl
EVAL_LLM_BASE_URL=... EVAL_LLM_API_KEY=... EVAL_LLM_MODEL=... uv run python -m evals.run_gates
```

Options: `--cases ID ...`, `--repeat N` (default 2; a case passes when every run matches),
`--min-pass-rate X` (default 0.9), `--json FILE`, `--recorded [FILE]`. Exit codes as for scoring.
CI runs the recorded replay on pull requests and the real model from the manual workflow.
