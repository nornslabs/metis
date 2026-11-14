# AGENTS.md

Entry point for any AI coding agent working on Metis. Read this first, then load only the context files the task needs.

## Approach

Metis is built incrementally with a spec-driven workflow. Context files define what to build and how; PRDs define the current unit of work; the progress tracker records state. Always implement against these files. Do not infer or invent behavior.

## Folder Structure

```text
/
├── AGENTS.md                  # this file
├── .agents/                   # everything agent-related lives here
│   ├── ctx/                   # project context (source of truth)
│   │   ├── project-overview.md  # what Metis is, flow, features, scope, success criteria
│   │   ├── architecture.md      # stack, boundaries, storage, auth, invariants
│   │   ├── server-context.md    # server primitives: processes, ports, enums, modules, agent graph, API/job/error conventions
│   │   ├── code-standards.md    # coding rules for Python, LangGraph, TypeScript, data, tests
│   │   └── ai-workflow-rules.md # AI workflow rules and conventions
│   ├── prds/                  # one file per unit of work (see PRDs)
│   └── progress-tracker.md    # done / in progress / open questions
├── compose.yaml               # local stack: postgres, redis, api, worker, scheduler, web
├── docker/                    # docker init scripts (e.g. init.sql)
├── opencode.json              # opencode configuration
├── .env.example               # environment variable template
├── dist/                      # build artifacts
├── server/                    # Python: FastAPI api, Arq worker, scheduler, LangGraph agent
│   ├── adapters/              # adapter layer
│   ├── agent/                 # agent graph
│   ├── core/                  # core domain
│   ├── entrypoints/           # API entrypoints
│   ├── modules/               # domain modules
│   ├── evals/                 # evaluation datasets
│   ├── prompts/               # prompt versions
│   ├── migrations/            # Alembic migrations
│   ├── tests/                 # tests
│   └── ...                    # other server files
└── web/                       # Next.js app
    ├── AGENTS.md              # web-specific agent instructions
    ├── app/                   # Next.js app router
    ├── components/            # React components
    └── lib/                   # utilities
```

Run everything locally with `docker compose up` from the root. `server/` and `web/` each have their own `Dockerfile`; `compose.yaml` wires them to Postgres (pgvector) and Redis.

All agent-related files (context, PRDs, tracker, prompts for coding agents, scratch notes) go under `.agents/`. Nothing agent-related goes in `server/` or `web/`.

## Which Context to Load

| Task                        | Load                                       |
| --------------------------- | ------------------------------------------ |
| Any task                    | `project-overview.md`, `code-standards.md` |
| Server, API, jobs, DB       | + `architecture.md`, `server-context.md`   |
| Agent graph, tools, prompts | + `architecture.md`, `server-context.md`   |
| Web UI                      | + `architecture.md`                        |

Always load the active PRD and `progress-tracker.md`. How PRDs are created and implemented: see "Workflow: Two Commands".

## PRDs

A PRD (product requirements document) defines one feature: what to build, for whom, and how to know it is done. Each PRD is the spec for one unit of work that can be built and verified on its own.

- Location: `.agents/prds/<type>-<name>.md`, e.g. `feat-health-route.md`, `fix-sse-reconnect.md`.
  - `<type>`: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`.
  - `<name>`: short kebab-case, the most relevant name for the work (2–4 words).
- Sections: **Source** (Linear id and URL), **Problem / Goal**, **User stories**, **Requirements**, **Out of scope**, **Touches** (folders/modules), **Dependencies** (other PRDs), **Acceptance criteria**, **Status** (`draft`, `in progress`, `done`).
- Work on one PRD at a time. Do not start a PRD whose dependencies are not done.

## Workflow: Two Commands

All work goes through two global skills. Every agent (Claude Code, Codex, Cursor, any other) follows the same steps below, whether it has the skill installed or is following this file by hand.

| Command                      | Input                                                               | Output                                            |
| ---------------------------- | ------------------------------------------------------------------- | ------------------------------------------------- |
| `/to-spec <LINEAR-ID>`       | A Linear issue id, e.g. `/to-spec SHIP-206`                         | A PRD in `.agents/prds/`. No code.                |
| `/implement-spec <PRD-PATH>` | A PRD path, e.g. `/implement-spec .agents/prds/chore-core-infra.md` | The implemented PRD on its own branch, committed after approval. |

Always run `/to-spec` first, review the PRD, then run `/implement-spec`. Never implement straight from a Linear issue or a chat request.

### `/to-spec <LINEAR-ID>`: Linear issue → PRD

1. **Fetch the issue** from Linear with its description, Agent notes, parent, sub-issues, milestone and blocked-by links.
2. **Check order.** If a blocked-by issue has no PRD with Status `done`, stop and report which issues must come first.
3. **Read context**: the context files for the task (see "Which Context to Load") and `progress-tracker.md`.
4. **Name the PRD.** Use the PRD path in the issue's Agent notes if there is one; otherwise pick `<type>-<name>.md` (see PRDs). One issue = one PRD. A parent issue with sub-issues gets one PRD per sub-issue, unless the user asks for one combined PRD.
5. **Write the PRD** in `.agents/prds/` with every section from PRDs, plus a **Source** line at the top: `Linear: <ID> · <issue URL>`. Map the issue's Steps to **Requirements**, its Acceptance criteria to **Acceptance criteria**, and its blocked-by issues to **Dependencies**. Add only what the issue or `.agents/ctx/` defines; put anything unclear under **Open questions** in the PRD.
6. **Set Status `draft`**, add the PRD to Next Up in `progress-tracker.md`, and stop. Report the PRD path, then ask its open questions in the chat, each with a recommended step (see "Open Questions"). Do not create a branch or write code.

### `/implement-spec <PRD-PATH>`: PRD → code

1. **Read the PRD** at the given path. If it does not exist or its Status is not `draft` or `in progress`, stop and report. If it has unresolved open questions, stop and ask them in the chat (see "Open Questions"); once answered, record the answers in the PRD and continue.
2. **Check dependencies.** Every PRD in **Dependencies** must be `done`; otherwise stop.
3. **Create the branch** from an up-to-date `main`, named like the PRD with a slash:
   `git checkout main && git pull && git checkout -b chore/core-infra`
4. **Read context**: `progress-tracker.md` and the context files for the task (see "Which Context to Load").
5. **Update the tracker, then build.** Set the PRD Status to `in progress`, update `progress-tracker.md` (Status block + PRD Board row with branch), then implement within the PRD's scope only.
6. **Verify**: acceptance criteria plus the checks in "Before Moving to the Next PRD".
7. **Finish**: set Status to `done`, update `progress-tracker.md` and sync docs (see Keeping Docs in Sync).
8. **Ask before committing.** Never commit or push without human approval. When coding is done, ask: "Should I commit and push to PR?" and wait for the answer.
9. **Commit only after approval**: commit all changes (code, tests, PRD, tracker, docs) on the branch with conventional commits, e.g. `chore(core-infra): add global settings`. Reference the Linear id from the PRD's Source line in the commit body. If asked to open a PR, follow "Pull Requests".
10. **Do not merge or push to `main`.**

## Pull Requests

Every pull request uses the template at `.github/PULL_REQUEST_TEMPLATE.md`. Never write a free-form PR body.

1. **Read the template** before writing the body; it is the source of truth for sections and checklist items.
2. **Fill every section**, keep its headings and order, and delete the `<!-- -->` guidance comments:
   - **Summary**: one paragraph on what the PR does and why.
   - **Linear**: the real issue id and URL from the PRD's Source line, e.g. `Closes linear issue: SHIP-206 — <url>`. No placeholder `SHIP-XXXX`.
   - **Spec**: the PRD path this PR implements.
   - **Scope**: copy **Touches** and **Out of scope** from the PRD.
   - **Before merging**: tick (`[x]`) only the checks you actually ran and saw pass; leave the rest unticked and say why in **Notes**.
   - **Notes**: trade-offs, known limitations, follow-ups. Write `None` if empty.
3. **One PR = one PRD = one branch.** The PR title is the conventional commit summary with the Linear id, e.g. `feat(auth): add workspace RLS (SHIP-206)`.
4. **Create it with a body file**, not inline text, so the template's markdown survives:
   `gh pr create --base main --title "<title>" --body-file <filled-template-path>`

One PRD = one branch. Never mix two PRDs on the same branch.

## Progress Tracker

`.agents/progress-tracker.md` is the shared memory between sessions. Keep it current; never batch updates to the end.

- **On start** of any PRD or flow: set Active PRD, Branch and Last updated; add or update its PRD Board row as `in progress`; remove it from Next Up.
- **On finish**: mark the row `done`, clear Active PRD, add one line to Session Notes on what was built.
- **Whenever something changes** mid-work: a new open question, a blocker (`blocked` status), or a design decision (add a row to Decisions with the why).
- **Before ending a session**: write in Session Notes where you stopped and the next step, so the next session can resume.
- Commit tracker changes together with the work on the PRD branch.

## Scoping Rules

- One PRD at a time; small, verifiable increments.
- Stay inside one system boundary per step (`web/`, an API module, a job, the agent graph).
- Follow module boundaries: other modules only via `service.py`; the agent only via services.

## When to Split Work

Split a step if it combines:

- Web UI changes and server changes.
- API/module changes and agent graph changes.
- More than one module's tables or migrations.
- A new specialist or tool and a new external integration.
- Behavior not defined in `.agents/ctx/` or the PRD.

If a change cannot be verified end to end quickly, the scope is too broad. Split it into another PRD.

## Handling Missing Requirements

- Never invent product behavior, scoring rules, enums or API shapes not in `.agents/ctx/`.
- If a requirement is ambiguous, propose the resolution in the relevant context file, then implement.
- If a requirement is missing, add it under **Open questions** in `progress-tracker.md`, ask it in the chat (see "Open Questions"), and stop that part of the work.

## Open Questions

Whenever an open question arises (in `/to-spec`, `/implement-spec` or mid-work), do not leave it only in a file. Ask the user in the chat, right then:

- One question at a time or a short numbered list; each stands on its own.
- Each question carries a **recommended step**: the option you would pick and why, listed first and marked "(Recommended)".
- Use the interactive question tool when available; otherwise plain chat text.
- After the answer, record it: remove it from **Open questions** in the PRD or tracker and, if it is a design choice, add a row to Decisions.
- Still list unresolved questions in the PRD and `progress-tracker.md` so the next session sees them.

## Protected Files

Do not modify unless explicitly instructed:

- `.agents/ctx/*` (except when syncing docs, below)
- `web/components/ui/*` (shadcn/ui generated components)
- Merged Alembic migrations in `server/migrations/`
- Existing prompt versions in `server/prompts/` (add a new version instead)
- `server/evals/` datasets
- Lock files (`uv.lock`, `package-lock.json`) except via the package manager

## Keeping Docs in Sync

Update the matching file in `.agents/ctx/` in the same change when you alter:

- Architecture, boundaries or invariants → `architecture.md`
- Enums, ports, modules, API/job/error conventions → `server-context.md`
- Coding conventions → `code-standards.md`
- Features or scope → `project-overview.md`

## Before Moving to the Next PRD

1. The PRD's acceptance checks pass end to end.
2. No invariant in `architecture.md` is violated.
3. Server: `uv run ruff check`, `uv run mypy`, `uv run pytest` pass.
4. Web: `npm run lint`, `npm run typecheck`, `npm run build` pass.
5. The PRD status and `progress-tracker.md` are updated.

## External Tools

- **Docs (source of truth for design):** Notion. Project pages live under [Projects](https://app.notion.com/p/41543c736c23814db62dd743520ca198). Metis design is split into [Metis HLD](https://app.notion.com/p/41543c736c23817787a0e5504448f089) (high-level: components, stack, build plan) and [Metis LLD](https://app.notion.com/p/41543c736c23816499c2e66bd6b82401) (low-level: modules, schema, state machine, contracts, agents, config, errors, tests). Sync any change to architecture, boundaries or invariants into `architecture.md` and the matching Notion page.
- **Issue tracking:** Linear. The Metis project is [`P-SHIP-3`](https://linear.app/heimdallabs/project/metis-5864eaf29689) (team `SHIP`). Create issues and milestones there via the Linear MCP integration; Metis stores only the returned ids.

## Notion Tool Selection (for agents)

Use the Notion Memory page **[Notion tool usage](https://app.notion.com/p/41543c736c2381f5a2dbc064086a307e)** as the reference. In short:
