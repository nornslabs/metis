# PRD: feat-optional-exa-llm-gate

Linear: SHIP-272 · https://linear.app/heimdallabs/issue/SHIP-272/server-llm-key-check-at-run-start-skip-research-without-an-exa-key

## Problem / Goal

A run in a workspace with no Exa key fails after the whole interview with `provider.not_configured` ("Provider Not Configured"). The user has chatted for a long time before learning that research cannot run.

Decided with the user:

- **LLM key is required, and must have passed its test.** Without a saved LLM key whose last test succeeded, a run cannot start.
- **Exa is optional.** Without an Exa key the Researcher does not call Exa or do any research. It tells the user, and the run ends as `succeeded`.
- The user can add the Exa key later and start a new run to do the research.

This PRD is server only. The web part (banner, blocked Start, notice row) is SHIP-273 and depends on this one.

## User stories

1. As a user with no working LLM key, I want Start to be refused with a clear reason before any run exists, so that I am not left with a failed run.
2. As a user with no Exa key, I want the interview to finish and the run to end cleanly with a note that research was skipped, so that I do not see a failure after a long chat.
3. As a user who adds an Exa key later, I want a new run to do the research, so that I do not have to start over.
4. As a client developer, I want a `notice` run event with a code and a text, so that the web can show the skip explicitly and a replayed stream shows it again.
5. As a user, I want provider errors that still happen to name the provider, so that I know which key to fix.

## Requirements

1. **LLM gate in `start_run`.** `ideas.service.workflow_runs.start_run` (through the `identity` module's public API) refuses to create a run unless the workspace has an `llm` provider key row with `last_test_ok is True`. It reads the row only: no decryption, no LLM call. It checks after the idea lookup and the idempotency lookup, so a repeated start with the same key still returns its run. It raises `LlmNotReadyError` (`provider.llm_not_ready`, status 402, not retryable) with `meta {reason: "not_configured" | "not_tested" | "test_failed"}`.
2. **Researcher skip.** At the start of the Researcher node, before any model or Exa work, it checks whether the workspace has an Exa key row (presence only). With none, it publishes a `notice` event, makes no Exa call and no snapshot, and ends the run without moving the stage and without looping back through the supervisor (a state flag read by `route`, so `route` returns `END`). The run ends `succeeded` through the existing end path.
3. **`notice` run event.** New `RunEventType.NOTICE` with data `{code, text}`. First code: `research.skipped_no_exa`, text "Research is skipped: Exa isn't set up." Published through `core.events`; `agent/run_events.py` forwards it from a custom stream event like `node_finished`.
4. **Save the stage (resume later).** When a specialist moves the graph stage, the new stage is also written to `ideas.stage`, through the `ideas` service and its fixed transition table (the agent reaches it only via services). The runner does this for every node update, in one place for real and stub specialists, and catches up from the checkpoint's stage when a run starts or resumes, so a crash between a node's checkpoint and the write does not leave the two apart. A skipped Researcher leaves the stage at `researching`, so a later run starts there and does the research instead of repeating the interview. Document this in `server-context.md` and `architecture.md`.
5. **Provider error text.** `ProviderNotConfiguredError` carries `meta {provider}` and a `detail` that names it ("Add your Exa key in Settings"). The title and code stay as they are.
6. **Docs.** Update `project-overview.md` and `architecture.md` (Exa optional, LLM key required and tested), and `server-context.md` (`notice` event, `LlmNotReadyError`, the Researcher skip, the new error code).
7. **Tests.** The graph stage move writes `ideas.stage` (and an invalid transition is refused); after a skip the idea stays at `researching` and a new run starts there; `start_run` refuses with each reason and allows a passing key; a repeated start returns its run; the Researcher skips with no Exa key (no Exa client, no snapshot, one `notice`, run `succeeded`); a run with a key behaves as before; the `notice` event is published and replayed from the stream.

## Out of scope

- Any web change (SHIP-273). The web stage badge starts moving as a side effect; no web code changes here.
- Running the key test automatically, or re-testing a key at start.
- Skipping research when the Exa key exists but is invalid (that stays a normal failure).
- The Scorer and later stages.

## Touches

- `server/metis/modules/ideas/` (`service/workflow_runs.py`, stage write via the ideas service)
- `server/metis/modules/identity/` (public API: a key-readiness read)
- `server/metis/agent/` (`specialists/researcher.py`, `state.py`, `supervisor.py`, `run_events.py`)
- `server/metis/core/` (`errors.py`, `events.py` event types)
- `server/tests/`, `.agents/ctx/` (`project-overview.md`, `architecture.md`, `server-context.md`)

## Dependencies

- feat-exa-researcher (done)
- feat-provider-keys (done)
- feat-runs-api (done)

## Acceptance criteria

1. `POST /v1/ideas/{id}/runs` with no LLM key, an untested key, or a key whose last test failed returns 402 `provider.llm_not_ready` with the matching `meta.reason`, and creates no run.
2. With a passing LLM key and no Exa key, a run finishes `succeeded` after the interview, its stream holds one `notice` event (`research.skipped_no_exa`), and no Exa request is made.
3. With both keys, the run behaves as before.
4. After the interview moves the stage, `ideas.stage` shows the new stage; after a skipped research it stays `researching`, and a new run (with an Exa key) starts at `researching`, without repeating the interview.
5. `uv run ruff check`, `uv run mypy` and `uv run pytest` pass.

## Open questions

None.

## Status

done
