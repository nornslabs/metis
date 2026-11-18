# PRD: feat-interviewer

Linear: SHIP-236 · https://linear.app/heimdallabs/issue/SHIP-236/18-interviewer-specialist-with-adaptive-questions

Milestone: M3 — Interview and discovery. Branch: `feat/interviewer`. Blocked by SHIP-225 (run engine: SHIP-228, SHIP-232, SHIP-234, all done). Blocks SHIP-238 (Researcher and interview interleaving).

## Problem / Goal

Every run still goes through a stub Interviewer: it moves the stage forward and asks the user nothing. Metis' core flow (project overview step 3) needs an interview about why the idea is needed, why it works, who pays and whether it can be built. The interview should change based on what the user has already said (success criterion 2) and stop once it has enough.

Goal: replace the Interviewer stub with a real tool-calling specialist. It asks one question at a time through `ask_user` (an `interrupt()`), saves every turn in the `ideas` module, skips topics already answered, stops when every topic is covered, when the user ends it, or after 8 questions, and then writes a structured `InterviewBrief` and moves the run to `researching`.

## User stories

1. As a founder, I want Metis to ask me about my idea after I submit it, so that the plan rests on my reasons and not only on my one-paragraph pitch.
2. As a founder, I want one question at a time, so that I can answer each one properly.
3. As a founder, I want short, neutral questions, so that I am not pushed toward an answer.
4. As a founder, I want Metis to skip what my idea text already says, so that I do not repeat myself.
5. As a founder, I want Metis to skip a topic my earlier answer already covered, so that the interview adapts to me.
6. As a founder, I want the interview to cover the problem, the target customer, the current alternatives, willingness to pay and feasibility, so that nothing important is missed.
7. As a founder, I want to answer "skip" to a question, so that I can pass on a topic I cannot answer yet.
8. As a founder, I want to say "That's enough" and have the interview end, so that I control how long it takes.
9. As a founder, I want at most 8 questions, so that the interview never drags on.
10. As a founder, I want the interview to end on its own when every topic has an answer, so that I am not asked filler questions.
11. As a founder, I want my answers kept if I reload the page or the worker restarts, so that I never answer twice.
12. As a founder, I want the question I see after a reload to be the same one I was asked, so that the run and the page agree.
13. As a founder, I want a run that is re-interviewed later (after advice) to know my earlier answers for this idea, so that it asks only about what changed or is missing.
14. As a founder, I want the interview summed up in a short brief, so that later steps (research, scoring) work from what I said.
15. As a founder, I want the brief to say which topics I skipped or left open, so that later steps know where evidence is thin.
16. As a founder, I want the run to move on to research once the interview is done, so that the pipeline keeps going without me pressing anything.
17. As a founder, I want a clear failed run if my workspace has no LLM key, so that I know what to fix.
18. As a workspace member, I want interview turns hidden from other workspaces, so that my idea stays private.
19. As a developer, I want interview turns stored in the `ideas` module and reached only through its service, so that module boundaries hold.
20. As a developer, I want the brief produced as structured output, so that no code parses free text.
21. As a developer, I want the question cap enforced in code, not only in the prompt, so that a model that ignores the prompt still stops.
22. As a developer, I want saving a question to be safe when the node re-runs on resume, so that a resume never creates a duplicate turn.
23. As a developer, I want the Interviewer built on the shared ReAct builder with an allow-list of three tools, so that it only does what it is allowed to.
24. As a developer, I want the Interviewer to use the run's LLM gateway, so that its token usage is recorded like any other call.
25. As a developer, I want the other six specialists to stay stubs, so that this change stays in one boundary.
26. As a developer, I want the new prompt as a new version file, so that runs stay traceable to the exact prompt text.
27. As a developer, I want tests driven by a scripted fake LLM through the `run_graph` job, so that the whole interview flow is tested without a real provider.
28. As an operator, I want the Interviewer's tool calls and questions to appear in the run's event stream, so that the live run view shows progress.

## Requirements

1. **Table `ideas.interview_turns`** (migration `0015_interview_turns`): `id` (uuid7), `workspace_id`, `idea_id` (FK `ideas.ideas`, cascade), `run_id` (FK `ideas.workflow_runs`, cascade), `position` (int, per idea, starts at 1), `topic` (text + CHECK over `InterviewTopic`), `source` (text + CHECK: `asked` | `noted`), `question` (text), `answer` (text, null until answered), `created_at`. RLS on `workspace_id` like every `ideas` table. Unique `(idea_id, position)`. Partial unique index: at most one unanswered `asked` turn per run (`(run_id) WHERE source = 'asked' AND answer IS NULL`). Index `(workspace_id, idea_id, position)`.
2. **Enum `InterviewTopic`**: `problem`, `solution`, `customer`, `payment`, `feasibility`, `other`. The coverage checklist is the first five (see Resolved for how "target user" and "current alternatives" map).
3. **Idea brief.** Stored on the idea as a nullable `interview_brief jsonb` column on `ideas.ideas` (added in migration `0015`; a later interview overwrites it, the turns keep the history). `InterviewBrief` (Pydantic, in the `ideas` module DTOs): `problem`, `target_customer`, `current_alternatives`, `willingness_to_pay`, `feasibility` (each a short string or `null` when not known), `covered` and `missing` (lists of `InterviewTopic`, computed from the saved turns, not from the model), `ended_by` (`coverage` | `user` | `cap`), `question_count`.
4. **Service** (`modules/ideas/service/interview.py`; caller's session, never commits, scoped by workspace id as well as RLS; exported through `ideas/__init__.py`):
   - `open_question(session, workspace_id, idea_id, run_id, topic, question)` → the turn. If the run already has an unanswered `asked` turn with the same question text, it is returned unchanged (idempotent for node re-runs); a different open question is a code error.
   - `answer_question(session, workspace_id, turn_id, answer)` → the turn; an already answered turn is returned unchanged.
   - `save_interview_turn(session, workspace_id, idea_id, run_id, topic, question, answer)` → a `noted` turn (coverage the model took from the idea text or an earlier answer without asking).
   - `list_turns(session, workspace_id, idea_id)` → turns in `position` order.
   - `interview_summary(session, workspace_id, idea_id)` → `{covered, missing, asked_in_run}` style coverage used by `recall_memory` and the brief.
   - `save_interview_brief(session, workspace_id, idea_id, brief)`.
   - A topic counts as covered when it has a turn with a non-empty answer that is not `skip` (case-insensitive, trimmed).
5. **Tools** (`agent/tools/interview.py`; each opens its own short transaction through the runner's session factory, like the gateway does):
   - `ask_user(question, topic)`: Interviewer variant. Refuses without interrupting when the run already asked 8 questions (returns a message telling the model to finish). Otherwise `open_question` (idempotent), then `interrupt({"type": "question", "question": question})` (payload unchanged so the runs API and the web keep working), then `answer_question` with the resume value and returns the answer. The existing generic `ask_user` in `agent/tools/ask_user.py` stays for other specialists.
   - `save_interview_turn(topic, question, answer)`: records a `noted` turn.
   - `recall_memory()`: v1 returns this idea's turns (topic, question, answer) and current coverage. No cross-idea memory.
   - `finish_interview(brief fields…, ended_by)`: the structured output. Its argument schema is the model-written part of `InterviewBrief`; the node fills `covered`, `missing` and `question_count` from the service. Using a tool for structured output keeps the `LLMProvider` port unchanged.
6. **Specialist** (`agent/specialists/interviewer.py`): built with `build_react_specialist` over the prompt, the four tools above and the run's chat model (`purpose="interview"`). Behaviour per stage:
   - `intake` → returns `stage: interviewing` with no model call (as the stub did).
   - `interviewing` → runs the ReAct loop seeded with the idea's title and raw text. When `finish_interview` is called it saves the brief and returns `stage: researching`. Step limit raised for this specialist so 8 questions plus recall, notes and finish fit (each question is two supersteps); hitting it fails the run with the existing step-limit behaviour.
   - Emits `node_finished` like the stubs; `step_count` is incremented once per node visit.
7. **Prompt** `metis/prompts/interviewer.v2.md` (v1 is protected and stays): one short, neutral question at a time; call `recall_memory` first; never ask a covered topic; when an answer covers more than one topic, record the extra topics with `save_interview_turn`; track the five-topic checklist; "skip" skips a topic; "That's enough" (or a clear wish to stop) ends the interview with `ended_by: user`; finish with `finish_interview` once every topic is covered or skipped, or when told the cap is reached. Untrusted-data rule kept.
8. **Runner wiring.** The runner builds one `LLMGateway` per run (closed when the stream ends) and the default specialists become: real Interviewer + stubs for the other six. `RunnerDeps.specialists` becomes a factory that receives the run's gateway and session factory, so tests still swap nodes. When `AGENT_STUB_SPECIALISTS` is true (config setting, default false; set in the e2e/CI compose environment) every specialist is a stub and no gateway is built. No workspace LLM key → `ProviderNotConfiguredError` → run `failed` with `provider.not_configured`. Provider failures fail the run with `provider.upstream_error` (existing mapping).
9. **Stage.** The Interviewer only changes the graph state's `stage`; it does not write `ideas.stage`.
10. **Docs.** `server-context.md` (table, enum, service functions, tools and their payloads, Interviewer behaviour, runner wiring, prompt v2), `architecture.md` if the gateway-per-run wiring changes the run flow description, tracker. Notion LLD sync follows.

## Out of scope

- Cross-idea user memory and a learning agent (`recall_memory` reads this idea only).
- The Researcher and interleaving research with the interview (SHIP-238).
- Real Scorer, Advisor, Architect, Planner, Integrator.
- Budget enforcement in USD (SHIP-237).
- Any web UI change (the existing question card already renders `interrupt` events); a UI for the brief or the turn history.
- An HTTP route to read interview turns or the brief.
- Editing or deleting past answers.
- Changing the `interrupt` payload shape or the resume API.

## Touches

`server/metis/modules/ideas/` (`models/interview.py`, `repo/interview.py`, `service/interview.py`, `dto/interview.py`, `__init__.py` exports, `models/ideas.py` for the brief column), `server/migrations/versions/0015_interview_turns.py`, `server/metis/agent/specialists/interviewer.py`, `server/metis/agent/tools/interview.py`, `server/metis/agent/runner.py` (gateway per run, specialist factory), `server/metis/core/config.py` (`AGENT_STUB_SPECIALISTS`), `compose.yaml` / `.github/workflows/ci.yml` / `.env.example` (stub setting for e2e), `server/metis/agent/graph.py` (only if the factory needs it), `server/metis/prompts/interviewer.v2.md`, `server/tests/agent/`, `server/tests/modules/ideas/`, `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`, `.agents/progress-tracker.md`.

## Testing Decisions

- **What a good test does:** drives the system from the outside and asserts what the user, the database and the event stream see: questions asked, events published, run status, saved turns, the saved brief, the final stage. It does not assert prompts, message lists or tool internals.
- **Seam (one, the highest):** the `run_graph` job (`execute_run`) on real Postgres as `metis_app` and real Redis, with the LLM faked at the HTTP boundary by `FakeLLMServer` (`httpx.MockTransport`) answering with a scripted list of chat completions, including tool calls. Resume is a second `execute_run` with `resume=<answer>`, exactly as the runs API enqueues it. Prior art: `tests/agent/test_run_graph_job.py`, `run_job_helpers.py`, `llm_helpers.py` (`FakeLLMServer`, `workspace_with_key`), `test_interrupts.py`.
- Tests planned at that seam:
  - Happy path: question → `awaiting_user` with the question as `pending_interrupt`, `interrupt` event; answer → next question; … → `finish_interview` → graph stage moves to `researching` and the stubs carry the run to `succeeded`, turns saved in order with answers, brief saved with `covered` = all five, `ended_by: coverage`.
  - Adapts: one answer covers two topics → the fake model notes the second topic; the next question is about a third topic; the brief shows both covered from one asked turn.
  - Cap: a fake model that keeps asking → the 9th `ask_user` does not interrupt, the model finishes, `ended_by: cap`, `question_count` 8.
  - User ends early: answer "That's enough" → finish with `ended_by: user`, `missing` lists the uncovered topics.
  - "skip": a skipped topic is in `missing`, not `covered`.
  - Re-run safety: resuming re-runs the node; still one turn per question (no duplicate rows); a crash-recovery continue does not re-ask.
  - Recall: a second run on the same idea starts with the earlier turns via `recall_memory`.
  - No LLM key → run `failed` with `provider.not_configured`; usage rows recorded for every model call.
  - Stub setting: with `AGENT_STUB_SPECIALISTS=true` a run with no LLM key goes all the way to `succeeded` as before.
  - RLS: turns of one workspace are invisible from another.
- **Migration test** `0015` up/down, prior art `tests/modules/ideas/test_workflow_runs_migration.py`.
- `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.

## Dependencies

- `feat-run-graph-job` (SHIP-228): done.
- `feat-runs-api` (SHIP-232): done.
- `feat-run-events-sse` (SHIP-234): done.
- `feat-llm-gateway` (SHIP-220), `feat-agent-graph-skeleton` (SHIP-223): done.
- Blocks: SHIP-238.

## Acceptance criteria

- [x] Questions change based on previous answers: a topic already covered (by the idea text, an earlier answer or an earlier run) is not asked again.
- [x] The interview ends when coverage is complete, when the user ends it, or at 8 questions (enforced in code).
- [x] An `InterviewBrief` is stored for the idea and the run's stage advances to `researching`.
- [x] Every asked question is saved before the pause and its answer after resume, with no duplicate turns on re-run or recovery.
- [x] Interview turns are workspace-isolated by RLS; migration `0015` upgrades and downgrades.
- [x] Tests above pass; `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass.
- [x] `server-context.md`, `architecture.md` (if changed) and the tracker are updated.

## Open questions

None open.

## Resolved

- The Interviewer moves only the graph state's stage; it does not write `ideas.stage`. Stage sync for every stage stays a separate issue (user, 2026-11-18).
- New setting `AGENT_STUB_SPECIALISTS` (bool, default false): when true the runner uses stubs for every specialist. It is set only in the e2e/CI compose environment so Playwright keeps running real stub runs without an LLM key (user, 2026-11-18).
- The brief is a nullable `interview_brief jsonb` column on `ideas.ideas`: the issue says to write it "to the idea".
- "skip" skips one topic (it goes to `missing`); "That's enough" ends the whole interview. Reading of Step 4 + Step 5.
- A `source` column (`asked` | `noted`) is added beyond the issue's column list, so the 8-question cap counts only questions the user was asked, not notes.
- Prompt goes in `metis/prompts/interviewer.v2.md`: v1 exists and existing prompt versions are protected (AGENTS.md); the issue's `server/prompts/` path is stale (SHIP-223 moved prompts).
- Coverage checklist = topics `problem`, `solution`, `customer`, `payment`, `feasibility`. "Target user" is `customer`, "willingness to pay" is `payment`, "current alternatives" is asked under `solution` (why this works better than what people use today). `other` is for notes outside the checklist.
- Structured output is a `finish_interview` tool call, not a new port method.
- The 8-question cap is per run (a later re-interview after advice gets its own 8).
- Saving a question before `interrupt()` is idempotent (one open asked turn per run, same text reused), because the node re-runs on resume.
- The `interrupt` payload stays `{type: "question", question}`; `topic` is stored on the turn, not sent.

## Built differently from the wording above, on purpose

- No `position` column: turns are ordered by their uuid7 `id`, so there is no per-idea counter to race on; the index is `(workspace_id, idea_id, id)`.
- `ended_by` is worked out in code from the saved turns (`user`, `coverage`, `cap`), not passed by the model, and a fourth value `model` means the loop ended without reaching any of them. `finish_interview` takes only the five findings; a model that never calls it still gets a brief (empty findings).
- "That's enough" is detected in code (`STOP_ANSWERS`): it does not cover a topic, and `ask_user` refuses further questions in that run.
- `InterviewCoverage` also carries `skipped` and `user_ended`; `coverage` means every checklist topic is answered or skipped.
- The service gained `finish_interview` (builds and stores the brief) and `get_interview_brief`.
- The runner streams with `subgraphs=True`: LangGraph drops a nested tool loop's model output otherwise. Only `messages` chunks from inside a specialist are published, named after the top-level node via `langgraph_checkpoint_ns`.
- `RunnerDeps.specialists` stays an override mapping (applied over the real Interviewer and the stubs) and a new `llm_http_client` factory lets tests point the gateway at a fake. `job_ctx` in tests defaults to all stubs.
- `AGENT_STUB_SPECIALISTS` is wired in `compose.yaml` (default false) and noted in `web/playwright.config.ts`: run e2e with `AGENT_STUB_SPECIALISTS=true docker compose up`. CI does not run Playwright, so `ci.yml` is unchanged.
- The `0013` downgrade test now drops `ideas.interview_turns` first, since it references runs.
- The service function is `interview_coverage(session, workspace_id, idea_id, run_id)` (not `interview_summary`): the run id is needed for the per-run question count and stop answer. `open_question` returns a `QuestionRefusal` (`cap_reached`, `user_ended`) instead of `None`, and returns the run's last asked turn when it is already answered (crash between saving the answer and the checkpoint), so recovery never saves a question twice.
- New catalog errors: `QuestionAlreadyOpenError` (`interview.question_open`, 409) and `InterviewTurnNotFoundError` (`interview.turn_not_found`, 404).
- `build_react_specialist` gained `finish_tools`: the loop ends right after `finish_interview` succeeds, so a model cannot keep asking after it finished.
- `STEP_LIMIT = 40` bounds each stretch between two pauses (LangGraph's recursion limit counts per invocation); the 8-question cap is what bounds the interview.
- Extra index `ix_interview_turns_run_id` (per-run lookups: open question, counts). `STOP_ANSWERS` also accepts the bare words "enough" and "stop" as a clear wish to stop.

## Status

done
