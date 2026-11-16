# PRD: feat-agent-graph-skeleton

Linear: SHIP-223 · https://linear.app/heimdallabs/issue/SHIP-223/15-agent-graph-skeleton-with-supervisor-and-checkpointer

Milestone: M2 — Ideas and agent run engine. Branch: `feat/agent-graph-skeleton`.

## Problem / Goal

Every agent run needs one LangGraph graph: a supervisor that routes work to specialists, state saved in Postgres so a run can pause for the user and resume later, and a step limit that stops runaway runs. None of this exists yet: `server/metis/agent/` holds only the LLM gateway (SHIP-220). The `run_graph` job and the runs API (SHIP-225) and the real specialists and tools (SHIP-233 and later) all build on this graph.

Goal: the single `StateGraph` with a deterministic supervisor, seven stub specialists, the `ask_user` / approval interrupt tools, a Postgres checkpointer, versioned prompt files with a loader, and tests proving stage routing, interrupt/resume and the step limit. No real LLM behaviour yet.

## User stories

1. As a developer, I want one graph that every run uses, so that new behaviour is a new node or tool, never a new graph.
2. As a developer, I want a `MetisState` with ids and summaries only, so that checkpoints stay small and nodes are safe to re-run.
3. As a developer, I want a supervisor that is a pure function of `stage`, so that routing is predictable and needs no LLM.
4. As a developer, I want the supervisor to route `intake → interviewing → researching → scoring → advising | spec_draft → spec_confirmed → planning → exported` through the matching specialist, so that a stub run walks every stage in order.
5. As a workspace owner, I want a run to stop with a clear error when it reaches the workspace's `max_steps`, so that a looping run cannot burn my budget.
6. As a workspace owner, I want `max_steps` read from my workspace settings (default 50), so that my cap applies to every run.
7. As a user, I want a run to pause when the agent needs my answer, so that the interview waits for me instead of guessing.
8. As a user, I want my answer to resume the run exactly where it paused, so that no work is repeated or lost.
9. As a user, I want a run that needs my approval before an external write to pause with an approval request, so that nothing is written to Linear or Notion without my consent.
10. As an operator, I want a paused run to resume from a fresh graph instance in a new process using only the checkpointer, so that a worker restart or another worker can continue it.
11. As an operator, I want the checkpoint tables created at worker startup, so that no manual step is needed to deploy.
12. As an operator, I want the checkpoint `thread_id` to be the run id, so that one run maps to one checkpoint thread.
13. As a developer, I want each specialist stub to move the stage forward and emit a `node_finished` custom event, so that the SSE stream (SHIP-225) has events to forward.
14. As a developer, I want a helper that builds a tool-calling ReAct-style subgraph from a prompt, a tool list and the gateway model, so that real specialists need only a prompt and tools.
15. As a prompt author, I want prompts as versioned files (`interviewer.v1.md`, …) with a loader, so that a prompt change is a new version, not an edit.
16. As a developer, I want the loader to fail clearly on a missing prompt or version, so that a typo does not become an empty system prompt.
17. As a developer, I want specialists to get chat models only through the `LLMGateway`, so that every call is metered.
18. As a developer, I want specialists to reach data only through module services, so that boundaries hold.
19. As a developer, I want `last_error` in state set when the supervisor ends a run early, so that the job and API can report why.
20. As a maintainer, I want graph tests with fake ports and no real LLM, so that CI spends nothing.

## Implementation Decisions

- **State.** `MetisState` is a `TypedDict` with `run_id`, `workspace_id`, `idea_id`, `stage` (`Stage`), `messages` (reducer `add_messages`), `summary`, `step_count`, `budget`, `pending_approval`, `last_error`. Ids and short summaries only; no documents or search results.
- **Supervisor.** A pure function `stage → next node name | END`, plus a step check: when `step_count` reaches the workspace's `max_steps` it ends the run and sets `last_error` to a domain error code (new `run.step_limit_reached`). It never calls an LLM, the DB or a module. `max_steps` enters the graph as input state (`budget`), loaded by the caller, so the supervisor stays pure. The caller reads it through the identity module's public surface.
- **Stage routing.** Stage → specialist: `intake`/`interviewing` → Interviewer, `researching` → Researcher, `scoring` → Scorer, `advising` → Advisor, `spec_draft`/`spec_confirmed` → Architect, `planning` → Planner, `exported` → Integrator is reached from `planning` after approval. The exact table follows the `Stage` transition table in `server-context.md`; stubs advance `stage` and a stub run visits every specialist including the Advisor (user decision): `scoring → advising → scoring → spec_draft`, the loop being the allowed rescore transition; see Resolved. The table lives in one place and is covered by a test.
- **Stage in state vs the idea row.** The graph's `stage` is the run's working copy. Stubs do not write `ideas.stage`; real specialists will call `ideas.transition` in later issues.
- **Specialists.** Seven nodes (Interviewer, Researcher, Scorer, Advisor, Architect, Planner, Integrator). Each is a stub that increments `step_count`, advances the stage and emits a `node_finished` custom stream event. A `specialists/base.py` helper builds the ReAct-style subgraph (prompt, tool list, gateway model, per-specialist step limit); stubs do not use it yet except a test that builds one with a fake model.
- **Interrupts.** `ask_user(question)` calls `interrupt({"type": "question", ...})`; approvals call `interrupt({"type": "approval", ...})`. The resume value comes back from `Command(resume=value)`. Payloads are small JSON objects with a `type`.
- **Checkpointer.** `AsyncPostgresSaver`, `thread_id` = run id. `build_graph(checkpointer)` takes it as an argument so tests can pass any saver. The worker's startup hook calls `setup()` once. The checkpoint tables are created by the library, not by Alembic, and live in a Postgres schema the app role can use.
- **Prompts.** Versioned Markdown files in `server/metis/prompts/` (inside the package, so the image already ships them; the empty `server/prompts/` folder and its Dockerfile `COPY` are removed) named `<specialist>.v<N>.md`, one per specialist, with a loader that returns the text of a given version (default: latest) and raises a clear error for an unknown prompt or version. Existing versions are never edited.
- **Gateway.** The graph never builds a model itself; specialists receive the `LLMGateway` (or a fake `LLMProvider`) when the graph is built. Stubs make no LLM call.
- **No module imports beyond the public surface.** The graph imports modules only through their `__init__.py`; the import-linter contracts stay green. Whether `agent` may import `ideas` and `identity` is already allowed by the gateway.
- **Out of the graph.** The `run_graph` job, run status updates, the Redis event stream and the runs API are SHIP-225. This PRD only exposes `build_graph` and the pieces it needs.
- **Docs.** `server-context.md` (Agent Graph: state fields, stub routing, interrupt payloads, prompt naming, checkpointer, new error code) and `architecture.md` if invariants change; Notion LLD synced.

## Testing Decisions

- **Seam:** the compiled graph (`build_graph(checkpointer)`), driven with `ainvoke` / `astream` and `Command(resume=...)`, against real Postgres for the checkpointer. This is the highest seam below the job. A good test checks what a caller sees: the order of stages and nodes visited, the interrupt payload, the final state, the stream events, the error code. It does not inspect node internals.
- Tests planned:
  - A stub run from `intake` visits every specialist in stage order and ends at `exported`.
  - Each specialist emits one `node_finished` custom event.
  - `ask_user` pauses the run with a `question` interrupt; `Command(resume=...)` continues with the answer; an approval interrupt does the same with `type: approval`.
  - Interrupt, then build a brand-new graph and checkpointer on the same database and resume by `thread_id` only: the run continues. (This stands in for "a new process".)
  - `max_steps` reached → the run ends with `last_error` code `run.step_limit_reached`; a run just under the limit completes.
  - The supervisor routing table maps every `Stage` to a node or `END` (parametrised over the `Stage` enum, so a new stage fails the test).
  - The prompt loader returns the latest version, returns a named version, and fails clearly on unknown names or versions.
  - The base ReAct helper runs a tool call with a fake `LLMProvider`.
  - `AsyncPostgresSaver.setup()` is idempotent (called twice, no error).
- **Prior art:** `tests/agent/test_llm_gateway.py` and `tests/agent/llm_helpers.py` (fake `LLMProvider`, real Postgres, no real calls); `tests/modules/conftest.py` for database readiness.
- `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.

## Out of Scope

- Real specialist behaviour, tool bodies other than `ask_user` and approval interrupts, MCP tool loading (SHIP-233), Exa tools (SHIP-226).
- The `run_graph` job, run status transitions, the `runs` table, the runs API and the SSE endpoint (SHIP-225).
- Budget enforcement against `llm_usage` (SHIP-237); only the step limit lands here.
- Market-watch graph entry (`stage=watch`).
- Writing `ideas.stage` from the graph; web changes.

## Touches

`server/metis/agent/` (`state.py`, `supervisor.py`, `graph.py`, `specialists/`, `tools/ask_user.py`, prompt loader), `server/metis/prompts/`, `server/Dockerfile` (drop the `prompts/` copy), `AGENTS.md` and `architecture.md` (prompt path), `server/metis/entrypoints/worker.py` (checkpointer `setup()` on startup), `server/metis/core/errors.py` (step-limit error), `server/pyproject.toml` + `uv.lock` (checkpoint driver if missing, via `uv`), `server/tests/agent/`, `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`.

## Dependencies

- `feat-llm-gateway` (SHIP-220): done.
- Blocks: SHIP-225 (`run_graph` job, runs API, SSE) and SHIP-233 (MCP tools in the graph).

## Acceptance criteria

- [x] A stub run goes through every stage in order, ending at `exported`.
- [x] An interrupt pauses the run and `Command(resume=...)` continues it from a fresh graph instance using only the checkpointer.
- [x] The supervisor stops the run with a clear error (`run.step_limit_reached`) when `max_steps` is hit.
- [x] Prompt files are versioned and the loader fails clearly on unknown names or versions.
- [x] Tests above pass; `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.
- [x] `server-context.md` (and `architecture.md` if needed) updated.

## Open questions

None open.

## Resolved

- Prompt folder: `server/metis/prompts/`; `server/prompts/` deleted (user, 2026-11-16).
- Checkpoint driver: add `psycopg[binary,pool]` with `uv`; the saver gets its own pool (user, 2026-11-16).
- Checkpoint tables: the library's `setup()` at worker start, no Alembic migration, no RLS (user, 2026-11-16).
- Stub path: visit every specialist including the Advisor (user, 2026-11-16).
- Advisor stub: returns to `scoring` once (allowed rescore loop), tracked by a `summary` marker; the second Scorer pass goes to `spec_draft`; the supervisor table equals the idea transition table (user, 2026-11-16).
- `max_steps`: the caller (SHIP-225's job) loads it from workspace settings and passes it in `budget`; tests pass it directly (user, 2026-11-16).

## Built differently from the wording above, on purpose

- Migration `0012_agent_checkpoints` was added: it only creates the `agent` schema and grants `metis_app` `USAGE, CREATE` plus default table privileges. Postgres 15+ forbids creating tables in `public` for non-owners, so the library's `setup()` could not run as the worker's role otherwise. The tables themselves are still created by `setup()`, not Alembic.
- `build_graph(checkpointer, specialists=None)` takes optional node overrides, so tests (and later real specialists) replace stubs by `Specialist`.
- The agent worker's `on_startup` is `agent_on_startup` (base startup + `setup_checkpointer`); job tests that have no Postgres derive their settings with the plain `on_startup`.
- `psycopg[binary,pool]` is a direct dependency (it was only transitive, without the C/binary wrapper).
- `Stage` comes back from a checkpoint as a plain string; nodes compare with `==`.

## Status

done
