# PRD: chore-ci-pipeline

**Source:** Linear: SHIP-210 · https://linear.app/heimdallabs/issue/SHIP-210/06-ci-pipeline

## Problem / Goal

Metis is built incrementally with a spec-driven workflow (see `AGENTS.md`). Every PRD must end with the checks in "Before Moving to the Next PRD": `ruff check`, `mypy`, `pytest` on the server; `lint`, `typecheck`, `build` on the web. Today those checks run only by hand, so `main` can sit green while a PR is actually broken. The goal: run lint, type checks, tests and builds on every pull request (and on pushes to `main`) so `main` stays green and every PR is verified before review.

## User stories

1. As a contributor, I want every PR to run the full server and web check suite automatically, so that I never land broken code on `main`.
2. As a contributor, I want a deliberate lint error to fail CI, so that the pipeline actually gates quality and is not a no-op.
3. As a contributor, I want the Dockerfiles to be built in CI, so that a broken build is caught before review.
4. As a contributor, I want a smoke step that starts the API and curls `/v1/health`, so that the running service is verified end to end.
5. As a maintainer, I want the whole pipeline to finish in under 10 minutes, so that feedback is fast and PRs do not pile up.
6. As a maintainer, I want a CI badge in `README.md`, so that the project's status is visible at a glance.

## Requirements

1. `.github/workflows/ci.yml` triggers on `pull_request` (all branches) and on `push` to `main`.
2. Job `server`:
   - Set up `uv` and Python 3.12, with cache.
   - `uv sync`, then `ruff check`, `mypy`, `pytest`.
   - Run `alembic upgrade head` before tests so the schema is current.
   - Service containers: `pgvector/pgvector:pg16` and `redis:7`, so tests that need Postgres (pgvector) and Redis pass.
3. Job `web`:
   - Node 22, npm cache, `npm ci`, then `lint`, `typecheck`, `build`.
4. Job `docker`:
   - Build both images (server and web) with `docker build` — no push — to catch Dockerfile breaks.
5. Smoke step: start the API and `curl /v1/health`; fail the job if the check does not return healthy.
6. Add a CI badge to `README.md` pointing at the workflow's status.

## Out of scope

- Deploys (M7) — CI builds images but does not push or deploy anywhere.
- Eval runs — scoring evals are added in M4, not here.
- Any job that requires secrets beyond what the repo already needs; no production credentials are introduced.
- Scheduling/nightly jobs beyond what is needed to keep `main` green.

## Touches

- `.github/workflows/ci.yml` (new)
- `README.md` (CI badge)

## Dependencies

- SHIP-204 · Scaffold monorepo and tooling (done)
- SHIP-208 · Health route (done)

Both are `done`; no open blockers.

## Acceptance criteria

1. A PR on a clean branch shows all jobs (`server`, `web`, `docker`, smoke) green.
2. A deliberate lint error makes CI fail.
3. Total CI time is under 10 minutes.
4. The workflow file is valid YAML and the jobs are named exactly `server`, `web`, `docker` with a smoke step that curls `/v1/health`.

## Status

done