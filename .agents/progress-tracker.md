# Progress Tracker

Agents update this file when they start a PRD, when they finish it, and whenever status, a decision or an open question changes. Keep entries one line each; newest first.

## Status

- **Phase:** Hackathon MVP — in progress (M0 Foundations)
- **Active PRD:** —
- **Branch:** —
- **Last updated:** 2026-11-12 — Completed CI pipeline (SHIP-210): added `.github/workflows/ci.yml` with server/web/docker/smoke jobs; README badge; fixed pre-existing ruff violations.

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
| chore-ci-pipeline | chore/ci-pipeline | done | SHIP-210: CI pipeline (server/web/docker jobs + smoke) |

Status values: `draft`, `in progress`, `blocked`, `done`.

## Next Up (MVP build order)

1. `feat-auth-workspaces` — Auth.js JWT, users, workspaces, RLS
2. `feat-provider-keys` — encrypted BYO LLM + Exa keys
3. `feat-ideas-crud` — ideas, stages, runs

## Open Questions

- None yet.

## Decisions

| Date       | Decision                                                                | Why                                                                       |
| ---------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| 2026-11-12 | One LangGraph graph: supervisor + 7 specialists with scoped tools       | Autonomous agents with controlled tool choice, interrupts and checkpoints |
| 2026-11-12 | Modular monolith, 3 processes (api, worker, scheduler)                  | 2 people, ~30 hours; modules can be split later                           |
| 2026-11-12 | Integrations via MCP (Linear, Notion)                                   | One pattern for every tool                                                |
| 2026-11-12 | OpenAI-compatible LLM adapter, Exa for research, BYO keys, free         | Pluggable providers, no hosting cost                                      |
| 2026-11-12 | Rubric fixed (25/25/15/15/10/10), adviser mode below 55, live rescoring | Comparable yet market-aware scores                                        |

## Session Notes

- Created PR #13 at https://github.com/nornslabs/metis/pull/13
- Fixed pre-existing ruff violations in `env.py`, `test_logging.py`, `test_config.py`