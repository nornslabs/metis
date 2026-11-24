# Flagsmith Non-Negotiables for Metis

**Date:** 2026-11-24
**Status:** Research complete — no implementation

---

## Metis Product Summary

Metis is an **agentic planning app** for solo hackers and startup founders. It turns a raw idea into a researched, scored, and buildable plan:

1. User signs in, adds BYO LLM key (required, OpenAI-compatible) + optional Exa key
2. Adaptive interview (why needed, why it works, who pays, feasibility)
3. Exa research → competitors + market facts with sources
4. Fixed-rubric score (6 params, 25/25/15/15/10/10 weights); <55 = adviser mode
5. User edits/confirms generated spec
6. For software: HLD → Notion, phases → tasks with dependencies → Linear export via MCP
7. Market watch rescans, rescores, suggests changes, rebalances Linear on approval

**Architecture:** Python (FastAPI, LangGraph, Arq) + Next.js (App Router, Tailwind, shadcn/ui). Monorepo with adapter pattern for all external dependencies.

---

## Current Adapter Pattern (from codebase)

| Adapter | Location | Providers |
|---------|----------|-----------|
| LLM | `server/metis/adapters/llm/` | OpenAI, Anthropic, Google, Ollama, custom OpenAI-compatible |
| MCP | `server/metis/adapters/mcp/` | Exa (research), Linear (export), Notion (planned) |
| STT | `server/metis/modules/stt/` | Sarvam (voice input) |

**Configuration:** pydantic-settings (`server/metis/core/config.py`) — env vars only, validated at startup, frozen after creation.

**Multi-tenancy:** Workspaces with Postgres RLS (`identity` module). Each workspace owns its encrypted provider keys (`identity.provider_keys`), settings (`run_budget_usd`, `max_steps`, Linear team), and runs.

**Agent graph:** 7 specialists (Interviewer, Researcher, Scorer, Advisor, Architect, Planner, Integrator) routed by Supervisor. Runs in Arq workers with Redis locks, LangGraph checkpoints in Postgres.

---

## External Dependencies Requiring Runtime Control

| Dependency | Criticality | Failure Modes |
|------------|-------------|---------------|
| LLM endpoints | **Required** — no run starts without valid key | Outages, rate limits, API deprecations, cost spikes, model retirements |
| Exa MCP | **Required for research** — runs complete without it (graceful skip) | MCP server down, auth expiry, rate limits, query failures |
| Sarvam STT | **Optional** — voice input only | API down, auth expiry, audio format issues |
| Linear MCP | **Required for export** — core value prop | OAuth token expiry, API changes, rate limits, webhook failures |
| Notion MCP | **Planned** — HLD export | Same as Linear |

**Current toggle:** Only `AGENT_STUB_SPECIALISTS` (env var, global, requires restart, no audit).

---

## Non-Negotiable #1: Kill Switches for Every External Dependency

### Requirement
Boolean flags per provider, togglable via dashboard with sub-second propagation, cached by SDK with configurable TTL.

### Flags needed
| Flag | Purpose |
|------|---------|
| `llm_enabled` | Master kill switch for all LLM calls |
| `llm_openai_enabled` / `llm_anthropic_enabled` / `llm_google_enabled` / `llm_local_enabled` | Per-provider granularity |
| `exa_enabled` | Research backbone on/off |
| `sarvam_enabled` | Voice input on/off |
| `linear_enabled` | Export integration on/off |
| `notion_enabled` | HLD export on/off (when implemented) |

### Why Metis specifically needs this
- **5+ external providers** with independent failure domains
- **BYO keys** = Metis doesn't control provider health, customer does
- **Worker architecture** = long-running graph executions; mid-run provider failure needs instant failover without redeploy
- **No bearer tokens** = session-cookie auth; can't use short-lived tokens for feature flags
- **Audit requirement** = who disabled what, when (compliance for customer data processing)

### Current gap
Env vars require container restart (docker compose / k8s rollout). No per-workspace targeting. No audit trail.

---

## Non-Negotiable #2: Per-Workspace Segmentation with JSON Config

### Requirement
JSON remote config values targeted by workspace attributes (workspace_id, user_id, role, tier, custom attributes) with gradual rollout (% of workspaces, specific IDs, segments).

### Config structures needed
```json
// Model routing per tier
{
  "model_routing": {
    "premium": "gpt-4o",
    "standard": "gpt-4o-mini",
    "free": "gpt-4o-mini",
    "fallback": "claude-3-haiku",
    "internal": "gpt-4o"
  }
}

// Rate limits per tier
{
  "rate_limits": {
    "personal": 10,
    "team": 100,
    "enterprise": 1000,
    "internal": 5000
  }
}

// Capability toggles per workspace
{
  "capabilities": {
    "voice_input": true,
    "web_search": false,
    "code_execution": true,
    "market_watch": false,
    "notion_export": false
  }
}

// Operational limits (already per-workspace in DB — Flagsmith should control dynamically)
{
  "run_budget_usd": 2.00,
  "max_steps": 50
}
```

### Why Metis specifically needs this
- **Workspace = tenant boundary** with RLS; all settings naturally scoped to workspace
- **Tiered product** (free/personal/team/enterprise) — different models, limits, capabilities per tier
- **Beta programs** — ship voice, code execution, market watch to % of workspaces or specific design partners
- **Operational tuning** — adjust `run_budget_usd`, `max_steps`, rate limits under load without redeploy
- **A/B testing** — compare model routing strategies, prompt versions, specialist behaviors
- **Gradual rollout** — new integrations (Notion), new specialist versions, new scoring rubrics

### Current gap
Settings live in Postgres (`identity.workspace_settings`), changed only via owner-initiated API call. No targeting, no gradual rollout, no A/B, no versioning.

---

## What Is Negotiable (Important but Not Blockers)

| Feature | Why Negotiable |
|---------|----------------|
| Audit log | Can build minimal audit in `core.events` outbox if needed |
| OpenFeature compatibility | Nice for vendor portability; adapter pattern already abstracts |
| Self-hosted Flagsmith | Can use hosted initially; self-host later if compliance requires |
| Gradual rollout % | Segmentation covers specific workspace IDs; % is convenience |
| Multivariate flags | JSON config + segmentation covers this use case |
| Webhooks / integrations | Metis already has outbox pattern; can relay flag changes |
| SSO / RBAC for Flagsmith dashboard | Internal tool; can gate via VPN/SSO at infra layer |

---

## Recommended Integration Approach

### Adapter Interface (fits existing pattern)
```python
# server/metis/adapters/feature_flags/base.py
class FeatureFlagProvider(Protocol):
    async def is_enabled(self, key: str, context: FlagContext) -> bool: ...
    async def get_string(self, key: str, context: FlagContext, default: str) -> str: ...
    async def get_json(self, key: str, context: FlagContext, default: dict) -> dict: ...
    async def close(self) -> None: ...

@dataclass(frozen=True)
class FlagContext:
    workspace_id: UUID
    user_id: UUID | None
    environment: str  # development, staging, production
    custom_attributes: dict[str, str]  # tier, role, beta_program, etc.
```

### Provider implementations
- `FlagsmithProvider` — primary (self-hostable, OpenFeature native)
- `LaunchDarklyProvider` — alternative
- `UnleashProvider` — alternative
- `StaticProvider` — dev/test (reads from env vars/config)

### Config registration
Add `FEATURE_FLAG_PROVIDER` to `server/metis/core/config.py` (like `AUTH_PROVIDER`, `CACHE_PROVIDER`, etc.)

### Usage in code
```python
# In LLM gateway (agent/llm.py)
async def chat_model(self, session, purpose):
    if not await flags.is_enabled("llm_enabled", context):
        raise ProviderNotConfiguredError("LLM disabled by feature flag")
    
    model = await flags.get_json("model_routing", context, {"default": "gpt-4o-mini"})
    selected_model = model.get(tier, model["default"])
    ...
```

---

## Sources (Primary)

| File | Relevance |
|------|-----------|
| `README.md` | Product overview, structure |
| `Agents.md` | Architecture, boundaries, workflow |
| `.agents/ctx/project-overview.md` | Goals, flow, features, scope |
| `.agents/ctx/architecture.md` | Stack, boundaries, run flow, storage, auth, invariants |
| `server/metis/core/config.py` | Pydantic settings, env vars, validation |
| `server/metis/adapters/llm/chat.py` | LLM adapter, OpenAI-compatible, error mapping |
| `server/metis/core/ports.py` | LLMProvider, Embedder protocols |
| `server/metis/agent/llm.py` | LLMGateway — per-run, per-workspace, usage recording |
| `server/metis/modules/identity/service/provider_keys.py` | BYO key storage, encryption, testing |
| `server/metis/modules/identity/dto/provider_keys.py` | ProviderKind (LLM, EXA, SARVAM), KeyReadiness |
| `server/metis/modules/identity/dto/settings.py` | Workspace settings (run_budget_usd, max_steps) |
| `server/metis/agent/supervisor.py` | Specialist routing, stage machine |
| `server/metis/agent/graph.py` | Graph compilation, specialist nodes |
| `server/metis/agent/tools/research_kb.py` | Researcher tools, Exa integration |
| `server/metis/modules/integrations/dto/providers.py` | IntegrationProvider (LINEAR, NOTION) |
| `web/components/settings/keys-panel.tsx` | UI for keys and run limits |

---

## Conclusion

Metis **requires** a feature flag service because:
1. **5+ external dependencies** with independent failure domains need instant kill switches
2. **Multi-tenant workspaces** with tiered product need JSON config + segmentation for model routing, rate limits, capabilities, and operational limits

**Flagsmith fits** because: self-hostable, OpenFeature native, supports both boolean flags and JSON remote config, has segmentation/gradual rollout, audit log.

**Integration path:** Add `FEATURE_FLAG_PROVIDER` adapter (like existing adapters), implement `FlagsmithProvider`, wire into LLM gateway, Researcher, Integrator, and settings service.