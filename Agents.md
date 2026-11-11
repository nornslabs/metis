# AGENTS.md

Entry point for any AI coding agent working on Metis. Read this first, then load only the context files the task needs.

## Approach

Metis is built incrementally with a spec-driven workflow. Context files define what to build and how; PRDs define the current unit of work; the progress tracker records state. Always implement against these files. Do not infer or invent behavior.

## External Tools

- **Docs (source of truth for design):** Notion. Project pages live under [Projects](https://app.notion.com/p/41543c736c23814db62dd743520ca198). Metis design is split into [Metis HLD](https://app.notion.com/p/41543c736c23817787a0e5504448f089) (high-level: components, stack, build plan) and [Metis LLD](https://app.notion.com/p/41543c736c23816499c2e66bd6b82401) (low-level: modules, schema, state machine, contracts, agents, config, errors, tests). Sync any change to architecture, boundaries or invariants into `architecture.md` and the matching Notion page.
- **Issue tracking:** Linear. The Metis project is [`P-SHIP-3`](https://linear.app/heimdallabs/project/metis-5864eaf29689) (team `SHIP`). Create issues and milestones there via the Linear MCP integration; Metis stores only the returned ids.

## Notion Tool Selection (for agents)

Use the Notion Memory page **[Notion tool usage](https://app.notion.com/p/41543c736c2381f5a2dbc064086a307e)** as the reference. In short:

| Task | Tool |
|---|---|
| Find page by name/content | `notion-search` (never `list_private_pages`/`list_recent_pages`) |
| Look up a person by name/email | `notion-search` with `query_type: "user"` |
| Read page, database, data source, doc | `notion-fetch` (accepts ID, URL, `notion://docs/*`) |
| Create page(s) under a parent | `notion-create-pages` with `parent: {page_id, type: "page_id"}` |
| Edit content (targeted) | `notion-update-page` with `command: "update_content"` |
| Edit full content/replace | `notion-update-page` with `command: "replace_content"` |
| Edit properties/icon/cover | `notion-update-page` with `command: "update_properties"` |
| Save durable context to Memory | `notion-create-pages` with `parent: "memory"` + `Type` in {Profile, Preference, Work, People, Notes} |
| Search Memory | `notion-memory-search` (or fetch id `"memory"` then query data source) |

**Never** invent Notion-flavored Markdown. Read `notion://docs/notion-flavored-markdown-spec` via `notion-fetch` before writing content.

## Folder Structure

```text
/
├── AGENTS.md                  # this file
├── .agents/                   # everything agent-related lives here
│   ├── ctx/                   # project context (source of truth)
│   │   ├── project-overview.md  # what Metis is, flow, features, scope, success criteria
│   │   ├── architecture.md      # stack, boundaries, storage, auth, invariants
│   │   ├── server-context.md    # server primitives: processes, ports, enums, modules, agent graph, API/job/error conventions
│   │   └── code-standards.md    # coding rules for Python, LangGraph, TypeScript, data, tests
│   ├── PRDs/                  # one file per unit of work (see PRDs)
│   └── progress-tracker.md    # done / in progress / open questions
├── compose.yaml               # local stack: postgres, redis, api, worker, scheduler, web
├── server/                    # Python: FastAPI api, Arq worker, scheduler, LangGraph agent
└── web/                       # Next.js app
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

Always load the active PRD and `progress-tracker.md`.

## PRDs

A PRD (product requirements document) defines one feature: what to build, for whom, and how to know it is done. Each PRD is the spec for one unit of work that can be built and verified on its own.

- Location: `.agents/PRDs/<type>-<name>.md`, e.g. `feat-health-route.md`, `fix-sse-reconnect.md`.
  - `<type>`: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`.
  - `<name>`: short kebab-case, the most relevant name for the work (2–4 words).
- Sections: **Problem / Goal**, **User stories**, **Requirements**, **Out of scope**, **Touches** (folders/modules), **Dependencies** (other PRDs), **Acceptance criteria**, **Status** (`draft`, `in progress`, `done`).
- Work on one PRD at a time. Do not start a PRD whose dependencies are not done.

## Working with a Spec

When given a PRD (a file or a request in chat), follow these steps in order:

1. **Name the PRD.** Pick `<type>-<name>.md` and save it in `.agents/PRDs/`. If the user wrote the PRD under another name, rename it; if the request came in chat, write the PRD from it using the sections above. Example: "add a health route to the API" → `.agents/PRDs/feat-health-route.md`.
2. **Create the branch** from an up-to-date `main`, named like the PRD with a slash:
   `git checkout main && git pull && git checkout -b feat/health-route`
3. **Read context**: the PRD, `progress-tracker.md`, and the context files for the task (see table above). Note any gaps as open questions before coding.
4. **Update the tracker, then build.** Set the PRD Status to `in progress`, update `progress-tracker.md` (Status block + PRD Board row with branch), then implement within the PRD's scope only.
5. **Verify**: acceptance criteria plus the checks in "Before Moving to the Next PRD".
6. **Finish**: set Status to `done`, update `progress-tracker.md`, and commit all changes (code, tests, PRD, tracker, synced docs) on the branch with conventional commits, e.g. `feat(health-route): add GET /v1/health`.
7. **Do not merge or push to `main`.** Leave the branch for review unless told otherwise.

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
- If a requirement is missing, add it under **Open questions** in `progress-tracker.md` and stop that part of the work.

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
