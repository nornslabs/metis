# PRD: feat-research-module

Linear: SHIP-229 · https://linear.app/heimdallabs/issue/SHIP-229/20-research-module-snapshots-items-and-competitor-knowledge-base

Milestone: M3 — Interview and discovery. Branch: `feat/research-module`. Blocked by SHIP-218 (`feat-ideas-crud`, done). Blocks SHIP-238 (Researcher specialist and interview interleaving). Related: SHIP-239 (web research panel).

## Problem / Goal

Metis promises research with sources (project overview, success criterion 3: "Research returns competitors with source links"). Nothing stores research today: there is no `research` module, no table for competitors or market facts, and no way for the score or the advice to cite a source. The same competitor found for two ideas in one workspace would also be looked up and stored twice.

Goal: add the `research` module (own `research` schema) that stores immutable, versioned **research snapshots** of sourced **research items**, a workspace-wide **competitor knowledge base (KB)** searched by vector similarity (pgvector) and by name, and the links between ideas and competitors. Expose the latest research of an idea and any snapshot through the API. Add an embeddings call to the LLM adapter and gateway so the Researcher (SHIP-238) can embed competitors and queries; when the workspace's provider has no embeddings, the KB still works by name and domain.

## User stories

1. As a founder, I want every competitor Metis shows me to have a source link, so that I can check it myself.
2. As a founder, I want every market fact Metis states to have a source link, so that I can trust the score and the advice built on it.
3. As a founder, I want each fact to carry the quote it came from, so that I can see exactly what the source said.
4. As a founder, I want each fact to carry a confidence, so that I can tell strong evidence from weak.
5. As a founder, I want to see when a source was published, so that I can spot stale facts.
6. As a founder, I want research items grouped by kind (competitor, market fact, trend, risk), so that I can read them by topic.
7. As a founder, I want to open my idea's latest research, so that I can read what Metis found without re-running anything.
8. As a founder, I want a one-paragraph summary at the top of the research, so that I get the gist before the details.
9. As a founder, I want to see the competitors of my idea with how much each one overlaps, so that I know who matters most.
10. As a founder, I want past research to stay exactly as it was, so that an old score can still be explained by the research it used.
11. As a founder, I want a re-run to create a new research version, not change the old one, so that I can compare versions.
12. As a founder, I want research still being gathered to stay out of "latest research", so that I never read a half-written result as final.
13. As a founder with several ideas, I want a competitor found for one idea to be reused for the next, so that research is faster and consistent.
14. As a founder, I want the same company found twice (e.g. `https://www.acme.com/pricing` and `acme.com`) stored once, so that my competitor list has no duplicates.
15. As a founder, I want a competitor's description and pricing refreshed when research finds newer details, so that the KB stays current.
16. As a founder, I want my competitor KB hidden from other workspaces, so that my research stays private.
17. As a workspace member, I want to read research of any idea in my workspace, so that the team sees the same evidence.
18. As a founder, I want an archived idea's research to be hidden like the idea, so that archive behaves the same everywhere.
19. As a founder whose LLM provider has no embeddings endpoint, I want the KB to still find competitors by name and domain, so that research works with any OpenAI-compatible provider.
20. As a founder, I want embedding calls counted in my usage, so that the budget covers all LLM spend.
21. As the Researcher agent (SHIP-238), I want to open a snapshot for my run, so that every item I find is tied to one research version.
22. As the Researcher agent, I want to open the same snapshot again when my node re-runs after a resume or a crash, so that a run never has two half-filled snapshots.
23. As the Researcher agent, I want saving a competitor or market fact without a URL refused, so that I am forced to cite.
24. As the Researcher agent, I want saving an item into a closed snapshot refused, so that I cannot change a finished version.
25. As the Researcher agent, I want to look up the KB by a query before searching the web, so that I reuse what the workspace already knows.
26. As the Researcher agent, I want to upsert a competitor and get its id back, so that I can link it to the idea in the snapshot.
27. As the Researcher agent, I want to close the snapshot with a summary, so that it becomes the idea's latest research.
28. As the Scorer and Advisor (later), I want to read the latest snapshot of an idea through the research service, so that I can cite its items.
29. As a developer, I want the research module reached only through its `__init__.py`, so that module boundaries hold.
30. As a developer, I want the research module to sit above `ideas` in the import-linter layers, so that it can check ideas but `ideas` never depends on research.
31. As a developer, I want the research module to never call an LLM itself, so that request handlers stay free of LLM calls (invariant 1) and the module is testable without a provider.
32. As a developer, I want RLS on every research table, so that a missed `WHERE workspace_id` cannot leak data.
33. As a developer, I want domain normalization in one pure helper, so that dedupe is predictable and unit-testable.
34. As a developer, I want the embedding dimension fixed at 1536 and checked, so that a provider returning another size never breaks an insert.
35. As a developer, I want a vector index on competitor embeddings, so that KB lookup stays fast as the KB grows.
36. As a web developer (SHIP-239), I want the research routes in the OpenAPI schema, so that the typed client gets them.

## Requirements

### Schema (migration `0016_research`, schema `research`, all tables RLS via `enable_tenant_rls`)

1. `research.snapshots`: `id` (uuid7), `workspace_id`, `idea_id` (FK `ideas.ideas`, cascade), `run_id` (FK `ideas.workflow_runs`, cascade), `summary` (text, null while open), `closed_at` (null while open), `created_at`. Partial unique index on `(run_id) WHERE closed_at IS NULL` (one open snapshot per run). Index `(workspace_id, idea_id, closed_at DESC)` for "latest".
2. `research.items`: `id` (uuid7), `workspace_id`, `snapshot_id` (FK, cascade), `kind` (`ResearchItemKind`: `competitor`, `market_fact`, `trend`, `risk`; text + CHECK), `title`, `url` (null allowed only for `trend` and `risk`; CHECK enforces it), `published_at` (date, null), `quote` (null), `claim`, `confidence` (numeric(3,2), 0–1, CHECK), `created_at`. Items are ordered by `id`.
3. `research.competitors`: `id` (uuid7), `workspace_id`, `name`, `url`, `domain` (normalized, see 9), `description` (null), `pricing` (null), `embedding vector(1536)` (null), `created_at`, `updated_at`. Unique `(workspace_id, domain)`. HNSW index on `embedding` with `vector_cosine_ops`. Index on `(workspace_id, lower(name))`.
4. `research.idea_competitors`: `workspace_id`, `idea_id` (FK, cascade), `competitor_id` (FK, cascade), `snapshot_id` (FK, cascade), `overlap` numeric(3,2), 0–1 (CHECK), `created_at`. Primary key `(snapshot_id, competitor_id)`.
5. The issue's column lists omit `workspace_id` on `items` and `idea_competitors`; it is added because every tenant row carries it and RLS policies key on it (architecture invariant).
6. Add the `pgvector` Python package (SQLAlchemy `Vector` type) through `uv add`.

### Module (`server/metis/modules/research/`, layers as in `code-standards.md`)

7. Public surface (`__init__.py`): `router`, `ResearchItemKind`, `NewResearchItem`, `NewCompetitor`, `Competitor`, `ResearchSnapshot`, `ResearchItem`, `KbMatch`, `EMBEDDING_DIMENSIONS` (1536), and the service functions below. Errors join `core/errors.py`.
8. Service functions (caller's session, never commit, scoped by workspace id as well as RLS, same rules as the ideas service):
   - `open_snapshot(session, workspace_id, idea_id, run_id)` → the run's open snapshot if one exists, else a new one. Unknown/archived idea → `IdeaNotFoundError`.
   - `add_item(session, workspace_id, snapshot_id, NewResearchItem)` → the item. `competitor`/`market_fact` without `url` → `ResearchSourceMissingError` (`research.source_missing`, 422). URL must be `http(s)`, ≤ 2,048 characters. Closed snapshot → `SnapshotClosedError` (`research.snapshot_closed`, 409). Unknown snapshot → `SnapshotNotFoundError` (`research.snapshot_not_found`, 404).
   - `link_competitor(session, workspace_id, snapshot_id, competitor_id, overlap)` → writes `idea_competitors` (idea from the snapshot); same closed/unknown rules; a repeat link updates `overlap`. Not named in the issue; needed to fill `idea_competitors`.
   - `close_snapshot(session, workspace_id, snapshot_id, summary)` → sets `summary` and `closed_at`. Already closed → `SnapshotClosedError`. Summary 1–4,000 characters.
   - `upsert_competitor(session, workspace_id, NewCompetitor{name, url, description?, pricing?, embedding?})` → `Competitor`. Dedupe on the normalized domain; an existing row keeps its id and `created_at`, takes the new `name`/`url`, takes `description`/`pricing`/`embedding` only when given (not null), and bumps `updated_at`. Race-safe (`INSERT … ON CONFLICT (workspace_id, domain) DO UPDATE`). An embedding whose length is not 1536 → `InvalidInputError` (422).
   - `kb_lookup(session, workspace_id, query, k, query_embedding=None)` → up to `k` `KbMatch{competitor, score, matched_by: "embedding"|"name"}`; `k` 1–20 (default 5). With an embedding: cosine-distance order over rows that have one, merged with case-insensitive name/domain substring matches, deduped by id, embedding matches first. Without one: name/domain matches only. Query trimmed, 1–200 characters.
   - `latest_snapshot(session, workspace_id, idea_id)` → newest **closed** snapshot with its items and linked competitors, or `None`.
   - `get_snapshot(session, workspace_id, snapshot_id)` → snapshot (open or closed) with items and competitors, or `SnapshotNotFoundError`. Snapshot of an archived idea → not found.
9. Domain normalization (`modules/research/helpers/domain.py`, pure): parse the URL (a bare host gets `https://`), lowercase the host, strip a leading `www.`, drop port, path, query and fragment; IDN hosts are punycode-encoded. No host → `InvalidInputError`. Subdomains other than `www` are kept (`docs.acme.com` ≠ `acme.com`) — no public-suffix list in MVP.
10. Validation (trimmed first, through `helpers.validation.validate_input`): item `title` 1–300, `claim` 1–2,000, `quote` ≤ 2,000, `confidence` 0–1 (2 decimals); competitor `name` 1–200, `description` ≤ 2,000, `pricing` ≤ 1,000.
11. Immutability: no service function updates or deletes an item, a link or a closed snapshot. Items and links are only written while their snapshot is open.

### Embeddings (adapter + gateway)

12. `adapters/llm/`: an `embed(texts) -> list[list[float]]` call on the OpenAI-compatible `/embeddings` endpoint (through `langchain_openai.OpenAIEmbeddings` or the `openai` client; only this package imports them), same error mapping to `UpstreamError` as chat. A 404, or a 400 naming an unknown model, maps to reason `not_supported` (new `FailureReason`).
13. `core/ports.py`: an `Embedder` protocol (`async embed(texts) -> list[list[float]]`, `async aclose()`).
14. `agent/llm.py`: `LLMGateway.embed(session, texts) -> list[list[float]] | None`. Uses the workspace `llm` key and `base_url` with the embedding model `LLM_EMBEDDING_MODEL` (env setting, default `text-embedding-3-small`). Records usage in `ideas.llm_usage` like chat calls (input tokens from the response, output 0). Returns `None` (and logs `llm.embeddings_unavailable` once per run) on `not_supported` or a vector whose length is not 1536; other `UpstreamError`s propagate. After one `not_supported`, the gateway stops calling embeddings for the rest of the run.
15. The research module never calls the gateway; callers (the Researcher tools, SHIP-238) embed first and pass vectors in.

### Routes (`modules/research/controller/`, all on `current_workspace`, any member reads)

16. `GET /v1/ideas/{idea_id}/research` → `ResearchView` of the latest closed snapshot; no closed snapshot → `404 research.not_found`; unknown/archived/foreign idea → `404 idea.not_found`.
17. `GET /v1/research/snapshots/{snapshot_id}` → `ResearchView` (open or closed); unknown/foreign/archived → `404 research.snapshot_not_found`.
18. `ResearchView`: `{id, idea_id, run_id, summary, closed_at, created_at, items: [{id, kind, title, url, published_at, quote, claim, confidence}], competitors: [{id, name, url, domain, description, pricing, overlap, updated_at}]}`. `workspace_id` and `embedding` are never returned. Items ordered by id; competitors by overlap descending, then name.

### Wiring and docs

19. Register the router in the API entrypoint. Import-linter: layers become `research → ideas → identity → auth`; add a contract "research uses only ideas', identity's and auth's public surface"; add `metis.modules.research` to the "auth imports no other domain module" list.
20. Errors added to `core/errors.py` and the error table in `server-context.md`. Regenerate the web OpenAPI types (`npm run gen:api`) so the CI drift check passes.
21. Docs in the same change: `server-context.md` (Research module section, `ResearchItemKind` primitive, errors, `Embedder` port, gateway `embed`, `LLM_EMBEDDING_MODEL`), `architecture.md` (import rule now includes `research`).

## Out of scope

- The Researcher specialist, its tools (`kb_lookup`, `kb_upsert_competitor`, `save_research_item`), its prompt and interview interleaving (SHIP-238).
- Market signals / `SignalKind` table and market watch.
- Web research panel (SHIP-239).
- Deleting or editing competitors through the API; any write route.
- Re-embedding existing competitors when the embedding model changes.
- Public-suffix-aware domain normalization (`acme.co.uk` vs `shop.acme.co.uk`).
- Budget enforcement for embedding calls (SHIP-237; this only records usage).

## Touches

`server/metis/modules/research/*` (new), `server/migrations/versions/0016_research.py`, `server/metis/adapters/llm/`, `server/metis/core/ports.py`, `server/metis/core/errors.py`, `server/metis/core/config.py` (`LLM_EMBEDDING_MODEL`), `server/metis/agent/llm.py`, `server/metis/entrypoints/api.py`, `server/pyproject.toml` (+ `uv.lock` via `uv add pgvector`), `server/tests/modules/research/*`, `server/tests/agent/test_llm_gateway.py`, adapter tests, `web/` generated OpenAPI types only, `.agents/ctx/server-context.md`, `.agents/ctx/architecture.md`.

## Testing Decisions

Good tests check behavior through the public surface (service functions, HTTP routes, the gateway), against real Postgres with RLS on, as the existing ideas tests do. They do not reach into repos or SQL.

Seams (highest available, all existing):

1. **Research service** (`metis.modules.research` functions on a real session) — most of the logic: dedupe by domain, URL required for competitor and market fact, closed snapshot refuses writes, one open snapshot per run (re-open returns the same), latest ignores open snapshots, `kb_lookup` with and without embeddings, embedding length check. Prior art: `tests/modules/ideas/test_interview_service.py`, `test_workflow_runs_service.py`.
2. **HTTP routes** (`httpx` against the app) — `ResearchView` shape, 404s (no research, unknown/archived/foreign idea, foreign snapshot), never returns `embedding`/`workspace_id`. Prior art: `tests/modules/ideas/test_ideas_api.py`, `test_runs_api.py`; route-auth walk in `tests/modules/auth/test_route_auth.py` covers the new routes automatically.
3. **Migration + RLS** — tables exist, constraints (URL CHECK, confidence CHECK, unique domain, open-snapshot index) and RLS isolation across two workspaces as `metis_app`. Prior art: `tests/modules/ideas/test_interview_turns_migration.py`.
4. **LLM gateway** (`LLMGateway.embed` with a fake HTTP client) — vectors returned, usage recorded, `not_supported` → `None` and no further calls, wrong dimension → `None`. Prior art: `tests/agent/test_llm_gateway.py`, `llm_helpers.py`.
5. **Domain helper** — pure unit table test (`www.`, case, port, path, bare host, IDN, no host).

## Dependencies

- `feat-ideas-crud` (SHIP-218) — done.
- Uses, all done: `feat-llm-gateway` (SHIP-220, gateway + usage), `feat-run-graph-job` (SHIP-228, `ideas.workflow_runs` for the `run_id` FK).

## Acceptance criteria

- [x] Every competitor and market fact has a source URL: the service refuses one without (`research.source_missing`), and the DB CHECK refuses it too.
- [x] The same competitor found twice (different URLs, same normalized domain) is stored once in a workspace; the second call updates it and returns the same id.
- [x] Latest research for an idea is readable through `GET /v1/ideas/{id}/research`, with items and competitors; an open snapshot is never returned as latest.
- [x] A closed snapshot cannot gain items or links, and cannot be closed again.
- [x] Opening a snapshot twice for one run returns the same snapshot.
- [x] `kb_lookup` finds a competitor by embedding similarity and by name; without embeddings it finds by name/domain.
- [x] `LLMGateway.embed` records usage and returns `None` when the provider has no embeddings.
- [x] RLS: workspace B cannot read workspace A's snapshots, items, competitors or links (service and API).
- [x] `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run lint-imports` pass; web `npm run typecheck` passes after `gen:api`.
- [x] `server-context.md` and `architecture.md` updated.

## Open questions

None.

## Resolved

1. **Scope of embeddings** (2026-11-18): the gateway `embed()` (adapter + `Embedder` port + `LLMGateway.embed`) stays in this PRD, as the issue's step 3 says; no agent tool uses it until SHIP-238.
2. **Embedding model** (2026-11-18): one env setting `LLM_EMBEDDING_MODEL` (default `text-embedding-3-small`, 1536 dims), used with the workspace's `llm` key and `base_url`.
3. **`overlap` type** (2026-11-18): numeric(3,2), 0–1 (CHECK), like `confidence`; competitors in a `ResearchView` are ordered by overlap descending, then name.
4. **No research yet** (2026-11-18): `GET /v1/ideas/{id}/research` returns `404 research.not_found`.

## Built differently from the wording above, on purpose

- `Embedder.embed` returns `EmbeddingBatch{vectors, input_tokens}` (not bare vectors), so the gateway can record usage; the gateway's `embed` still returns `list[list[float]] | None`. A wrong vector size also turns embeddings off for the run, like `not_supported`.
- New error `CompetitorNotFoundError` (`research.competitor_not_found`, 404) for `link_competitor` with an unknown or foreign competitor.
- `KbMatch.score` is the cosine similarity for embedding matches and `null` for name matches (a name match has no meaningful score).
- `helpers/domain.py` also holds `web_url` (URL validation for the DTOs) next to `normalize_domain`. A competitor URL may be a bare host (`acme.com` → `https://acme.com`); a URL needs a dotted host, so `localhost` is refused.
- The embedder uses the `openai` client directly (not `OpenAIEmbeddings`, which tokenizes with `tiktoken`); openai 3 is typed for `httpx2`, so passing the run's `httpx` client needs one `type: ignore`.

## Status

done
