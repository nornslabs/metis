# Progress Tracker

Agents update this file when they start a PRD, when they finish it, and whenever status, a decision or an open question changes. Keep entries one line each; newest first.

## Status

- **Phase:** Hackathon MVP — in progress (M0 Foundations)
- **Active PRD:** feat-global-logger
- **Branch:** feat/global-logger
- **Last updated:** 2026-11-12 — Completed global logger: added core/logging.py with configure_logging, get_logger, bind_context, clear_context; added core/middleware.py with RequestContextMiddleware; updated all entrypoints to configure logging at startup; added T201 ruff rule for no print; 543 lines added across 10 files; 64 tests pass.

## External Tools

- **Docs:** Notion — `Projects` page with `Metis` → `Metis HLD` + `Metis LLD` sub-pages.
- **Issue tracking:** Linear — Metis project `P-SHIP-3` (team `SHIP`), https://linear.app/heimdallabs/project/metis-5864eaf29689

## PRD Board

| PRD | Branch | Status | Notes       |
| --- | ------ | ------ | ----------- |
| feat-global-logger | feat/global-logger | done | SHIP-260: structlog with request context middleware; merged |
| chore-core-errors | chore/core-errors | done | SHIP-261: global error handler + error code catalog; merged onto `core/config.py` |
| chore-core-config | chore/core-config | done | SHIP-259: Pydantic Settings global config |
| chore-repo-setup | integration/v1-foundations | done | SHIP-204: Monorepo skeleton and tooling |
| chore-compose-stack | chore/compose-stack | done | SHIP-205: docker compose up for full local stack |
| feat-health-route | feat/health-route-refactored | done | SHIP-208: `GET /v1/health` with proper controller-service separation |

Status values: `draft`, `in progress`, `blocked`, `done`.

## Next Up (MVP build order)

1. `chore-core-config` — Pydantic Settings, .env.example, validation (SHIP-259)
2. `feat-health-route` — `GET /v1/health` (DB + Redis) (SHIP-208)
3. `feat-auth-workspaces` — Auth.js JWT, users, workspaces, RLS
4. `feat-provider-keys` — encrypted BYO LLM + Exa keys
5. `feat-ideas-crud` — ideas, stages, runs
6. `feat-agent-graph-skeleton` — supervisor graph, checkpointer, `run_graph`, SSE stream
7. `feat-interviewer` — adaptive interview with `ask_user` interrupt
8. `feat-exa-researcher` — Exa tools, snapshots, competitor KB
9. `feat-scorer` — rubric, `submit_scores`, score runs, bands
10. `feat-advisor` — suggestions below 55
11. `feat-spec-editor` — spec draft, versions, confirm
12. `feat-planner` — phases, tasks, dependencies, estimates
13. `feat-mcp-connections` — MCP OAuth, tool discovery
14. `feat-linear-export` — approval interrupt, Linear export via MCP
15. `feat-rescan-button` — manual "re-check market" rescore
16. `feat-web-idea-flow` — idea, interview, live progress, score card, spec, plan, export screens

## Open Questions

- None yet.

## Decisions

| Date       | Decision                                                                | Why                                                                       |
| ---------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| 2026-11-12 | Global logger: structlog with request context middleware                | One unified logging pipeline for all services; request tracing            |
| 2026-11-11 | One LangGraph graph: supervisor + 7 specialists with scoped tools       | Autonomous agents with controlled tool choice, interrupts and checkpoints |
| 2026-11-11 | Modular monolith, 3 processes (api, worker, scheduler)                  | 2 people, ~30 hours; modules can be split later                           |
| 2026-11-11 | Integrations via MCP (Linear, Notion)                                   | One pattern for every tool                                                |
| 2026-11-11 | OpenAI-compatible LLM adapter, Exa for research, BYO keys, free         | Pluggable providers, no hosting cost                                      |
| 2026-11-11 | Rubric fixed (25/25/15/15/10/10), adviser mode below 55, live rescoring | Comparable yet market-aware scores                                        |

## Session Notes

- Context files live in `.agents/ctx/`; workflow rules in `AGENTS.md`.