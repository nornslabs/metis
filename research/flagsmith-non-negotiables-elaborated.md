# Flagsmith Non-Negotiables for Metis — Elaborated Analysis

**Date:** 2026-11-24
**Status:** Research complete — elaborated for implementation planning
**Based on:** `research/flagsmith-non-negotiables.md`

---

## Executive Summary

Metis is a multi-tenant agentic planning platform with 5+ external dependencies and tiered workspace product. It **requires** a feature flag service for two architectural reasons:

1. **Kill switches** — 5+ independent failure domains need sub-second disable without redeploy
2. **Segmented JSON config** — Workspace-tiered model routing, rate limits, capabilities need dynamic targeting

This document elaborates the requirements, implementation architecture, and integration points for the Metis engineering team.

---

## Part 1: Kill Switches — Deep Dive

### 1.1 Dependency Failure Domain Analysis

| Dependency | Failure Domain | Blast Radius | Current Mitigation | Gap |
|------------|----------------|--------------|-------------------|-----|
| **OpenAI API** | Auth, rate limit, model deprecation, regional outage, pricing change | All runs for workspaces using OpenAI | Key test at save time; `AGENT_STUB_SPECIALISTS` env var | Global, restart required, no per-workspace |
| **Anthropic API** | Same as OpenAI | Workspaces using Anthropic | Same | Same |
| **Google Vertex/Gemini** | Same + quota exhaustion | Workspaces using Google | Same | Same |
| **Local/Ollama** | GPU OOM, model not loaded, version mismatch | Self-hosted workspaces | Same | Same |
| **Exa MCP** | MCP server down, auth expiry, rate limit, schema change | All research-dependent runs | Graceful skip (run completes without research) | No instant toggle, no gradual rollout |
| **Sarvam STT** | API down, auth expiry, audio format | Voice input only | Optional; UI shows disabled state | No kill switch |
| **Linear MCP** | OAuth expiry, API breaking change, rate limit, webhook failure | Export (core value prop) | Per-workspace connection; token refresh | No instant disable if Linear has incident |
| **Notion MCP** (planned) | Same as Linear | HLD export | Not implemented | Will need same |

### 1.2 Required Flag Taxonomy

```
metis.kill_switches.llm.enabled                    # Master LLM kill switch
metis.kill_switches.llm.providers.openai           # Per-provider granularity
metis.kill_switches.llm.providers.anthropic
metis.kill_switches.llm.providers.google
metis.kill_switches.llm.providers.local
metis.kill_switches.exa.enabled                    # Research backbone
metis.kill_switches.sarvam.enabled                 # Voice input
metis.kill_switches.linear.enabled                 # Export integration
metis.kill_switches.notion.enabled                 # HLD export (future)
```

### 1.3 Propagation Requirements

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| Dashboard → SDK cache | < 5 seconds | Worker runs can be 30+ minutes; mid-run failure needs fast failover |
| SDK cache TTL | Configurable (default 30s) | Balance API calls vs freshness |
| Cache invalidation on flag change | Push (webhook) or poll | Flagsmith supports both |
| Graceful degradation | Per-flag behavior | `exa_enabled=false` → skip research; `llm_enabled=false` → fail fast with clear error |

### 1.4 Integration Points in Codebase

| Location | Current Behavior | With Kill Switch |
|----------|------------------|------------------|
| `agent/llm.py:LLMGateway.chat_model()` | Builds model from workspace key | Check `llm_enabled` + provider flag before building |
| `agent/llm.py:LLMGateway.embed()` | Builds embedder from workspace key | Check `llm_enabled` + provider flag |
| `adapters/mcp/exa.py:ExaMcpClient` | Called by Researcher tools | Check `exa_enabled` before any call |
| `modules/stt/service.py` | Sarvam client for transcription | Check `sarvam_enabled` |
| `modules/integrations/service/connections.py:get_mcp_client()` | Returns Linear/Notion MCP client | Check `linear_enabled` / `notion_enabled` |
| `agent/tools/export_linear.py` | Linear export tools | Guarded by `linear_enabled` |
| `agent/tools/export_writes.py` | Notion export tools (future) | Guarded by `notion_enabled` |

### 1.5 Error Handling Strategy

```python
# In LLMGateway.chat_model()
async def chat_model(self, session, purpose):
    # Kill switch check — fail fast with actionable error
    if not await self._flags.is_enabled("metis.kill_switches.llm.enabled", self._context):
        raise ProviderNotConfiguredError(
            "LLM disabled by platform operator",
            meta={"reason": "kill_switch", "flag": "metis.kill_switches.llm.enabled"}
        )
    
    # Per-provider check
    provider = self._detect_provider(credentials.base_url)
    if not await self._flags.is_enabled(f"metis.kill_switches.llm.providers.{provider}", self._context):
        raise ProviderNotConfiguredError(
            f"{provider} disabled by platform operator",
            meta={"reason": "kill_switch", "flag": f"metis.kill_switches.llm.providers.{provider}"}
        )
    ...
```

---

## Part 2: Per-Workspace Segmentation with JSON Config — Deep Dive

### 2.1 Workspace Tier Model (Current + Planned)

| Tier | Workspace Type | Model Access | Rate Limits | Capabilities | Budget |
|------|----------------|--------------|-------------|--------------|--------|
| **free** | Personal, no payment | gpt-4o-mini only | 10 req/min | Interview, research, score | $2/run |
| **personal** | Solo founder | gpt-4o-mini + fallback | 30 req/min | + voice, code_exec | $5/run |
| **team** | Startup team (2-10) | gpt-4o + fallback | 100 req/min | + market_watch, web_search | $10/run |
| **enterprise** | Company (10+) | All models + custom | 1000 req/min | All + SSO, audit, custom rubrics | $50/run |
| **internal** | Metis team | Unrestricted | Unlimited | All + debug, experimental | Unlimited |

### 2.2 JSON Config Structures

#### 2.2.1 Model Routing Config
```json
{
  "model_routing": {
    "tiers": {
      "free": { "primary": "gpt-4o-mini", "fallback": "claude-3-haiku" },
      "personal": { "primary": "gpt-4o-mini", "fallback": "claude-3-haiku" },
      "team": { "primary": "gpt-4o", "fallback": "claude-3-5-sonnet" },
      "enterprise": { "primary": "gpt-4o", "fallback": "claude-3-5-sonnet", "custom": true },
      "internal": { "primary": "gpt-4o", "fallback": "claude-3-5-sonnet", "experimental": true }
    },
    "purpose_overrides": {
      "score": { "free": "gpt-4o-mini", "team": "gpt-4o" },
      "research": { "free": "gpt-4o-mini", "team": "gpt-4o" },
      "interview": { "all": "gpt-4o-mini" }
    },
    "embedding_model": "text-embedding-3-small"
  }
}
```

#### 2.2.2 Rate Limit Config
```json
{
  "rate_limits": {
    "tiers": {
      "free": { "requests_per_minute": 10, "tokens_per_minute": 50000, "concurrent_runs": 1 },
      "personal": { "requests_per_minute": 30, "tokens_per_minute": 150000, "concurrent_runs": 2 },
      "team": { "requests_per_minute": 100, "tokens_per_minute": 500000, "concurrent_runs": 5 },
      "enterprise": { "requests_per_minute": 1000, "tokens_per_minute": 2000000, "concurrent_runs": 20 },
      "internal": { "requests_per_minute": 10000, "tokens_per_minute": 10000000, "concurrent_runs": 100 }
    },
    "burst_multiplier": 2.0,
    "enforcement": "redis_sliding_window"
  }
}
```

#### 2.2.3 Capability Config
```json
{
  "capabilities": {
    "voice_input": { "free": false, "personal": true, "team": true, "enterprise": true, "internal": true },
    "web_search": { "free": false, "personal": false, "team": true, "enterprise": true, "internal": true },
    "code_execution": { "free": false, "personal": true, "team": true, "enterprise": true, "internal": true },
    "market_watch": { "free": false, "personal": false, "team": true, "enterprise": true, "internal": true },
    "notion_export": { "free": false, "personal": false, "team": false, "enterprise": true, "internal": true },
    "linear_export": { "free": true, "personal": true, "team": true, "enterprise": true, "internal": true },
    "custom_rubrics": { "free": false, "personal": false, "team": false, "enterprise": true, "internal": true },
    "shared_competitor_kb": { "free": true, "personal": true, "team": true, "enterprise": true, "internal": true }
  }
}
```

#### 2.2.4 Operational Limits Config (Dynamic Override of DB Settings)
```json
{
  "operational_limits": {
    "run_budget_usd": { "free": 2.00, "personal": 5.00, "team": 10.00, "enterprise": 50.00, "internal": 100.00 },
    "max_steps": { "free": 30, "personal": 50, "team": 100, "enterprise": 200, "internal": 500 },
    "interview_max_questions": { "free": 5, "personal": 8, "team": 12, "enterprise": 20, "internal": 30 },
    "research_max_sources": { "free": 10, "personal": 20, "team": 50, "enterprise": 100, "internal": 200 }
  }
}
```

### 2.3 Segmentation Strategy

#### 2.3.1 Targeting Dimensions
| Dimension | Source | Values | Example |
|-----------|--------|--------|---------|
| `workspace_id` | Request context | UUID | Exact workspace targeting |
| `user_id` | Request context | UUID | Per-user beta |
| `tier` | `identity.workspace_settings.tier` (new column) | free/personal/team/enterprise/internal | Tier-based config |
| `role` | `identity.members.role` | owner/admin/member | Owner-only features |
| `beta_program` | `identity.workspace_settings.beta_programs` (JSON array) | ["voice", "code_exec", "market_watch"] | Opt-in betas |
| `environment` | `APP_ENV` | development/staging/production | Env-specific config |
| `region` | Workspace metadata (future) | us-east/eu-west/ap-south | Regional compliance |

#### 2.3.2 Flag Evaluation Priority
1. Exact `workspace_id` match
2. `beta_program` membership
3. `tier` match
4. `environment` match
5. Default (all workspaces)

### 2.4 Integration Points in Codebase

| Location | Current Behavior | With JSON Config |
|----------|------------------|------------------|
| `agent/llm.py:LLMGateway.chat_model()` | Uses workspace's saved `model` | Resolve model from `model_routing[purpose][tier]` |
| `agent/llm.py:LLMGateway.embed()` | Uses `LLM_EMBEDDING_MODEL` from settings | Resolve from `model_routing.embedding_model` |
| `core/redis.py` / rate limiting | Fixed limits or per-workspace DB | Resolve from `rate_limits[ tier ]` |
| `agent/tools/` (voice, web_search, code_exec) | Enabled if key present | Check `capabilities[feature][tier]` |
| `modules/identity/service/settings.py` | DB `run_budget_usd`, `max_steps` | Override with `operational_limits[tier]` |
| `modules/integrations/` (Linear, Notion) | Enabled if connected | Check `capabilities[export][tier]` |

### 2.5 Context Building for Flag Evaluation

```python
# In a shared location: metis/core/feature_flags/context.py
@dataclass(frozen=True)
class FlagContext:
    workspace_id: UUID
    user_id: UUID | None
    tier: str  # free/personal/team/enterprise/internal
    role: str  # owner/admin/member
    beta_programs: tuple[str, ...]
    environment: str
    region: str | None = None

def build_flag_context(
    workspace_id: UUID,
    user_id: UUID | None,
    membership: Membership,  # from identity.deps
    workspace_settings: WorkspaceSettingsView  # from identity.service
) -> FlagContext:
    return FlagContext(
        workspace_id=workspace_id,
        user_id=user_id,
        tier=workspace_settings.tier or "free",
        role=membership.role.value,
        beta_programs=tuple(workspace_settings.beta_programs or []),
        environment=get_settings().app_env,
    )
```

---

## Part 3: Implementation Architecture

### 3.1 Adapter Interface (New File)

```python
# server/metis/adapters/feature_flags/base.py
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

@dataclass(frozen=True)
class FlagContext:
    workspace_id: UUID
    user_id: UUID | None
    tier: str
    role: str
    beta_programs: tuple[str, ...]
    environment: str
    region: str | None = None
    custom_attributes: Mapping[str, str] = ()

class FeatureFlagProvider(Protocol):
    async def is_enabled(self, key: str, context: FlagContext) -> bool: ...
    async def get_string(self, key: str, context: FlagContext, default: str) -> str: ...
    async def get_json(self, key: str, context: FlagContext, default: Mapping[str, object]) -> Mapping[str, object]: ...
    async def get_all_flags(self, context: FlagContext) -> Mapping[str, object]: ...
    async def close(self) -> None: ...
```

### 3.2 Provider Implementations

| Provider | Location | Notes |
|----------|----------|-------|
| `FlagsmithProvider` | `adapters/feature_flags/flagsmith.py` | Primary — uses Flagsmith Python SDK |
| `LaunchDarklyProvider` | `adapters/feature_flags/launchdarkly.py` | Alternative |
| `UnleashProvider` | `adapters/feature_flags/unleash.py` | Alternative |
| `StaticProvider` | `adapters/feature_flags/static.py` | Dev/test — reads from config/env |

### 3.3 Config Registration

```python
# server/metis/core/config.py — add to Settings class
feature_flag_provider: str = Field(
    default="static",
    validation_alias="FEATURE_FLAG_PROVIDER",
)  # "flagsmith" | "launchdarkly" | "unleash" | "static"

flagsmith_api_key: str | None = Field(
    default=None,
    validation_alias="FLAGSMITH_API_KEY",
)
flagsmith_env_id: str | None = Field(
    default=None,
    validation_alias="FLAGSMITH_ENV_ID",
)
flagsmith_base_url: str | None = Field(
    default=None,  # For self-hosted
    validation_alias="FLAGSMITH_BASE_URL",
)
```

### 3.4 Factory & Dependency Injection

```python
# server/metis/adapters/feature_flags/__init__.py
from metis.adapters.feature_flags.base import FeatureFlagProvider, FlagContext
from metis.adapters.feature_flags.static import StaticProvider
from metis.core.config import get_settings

async def build_feature_flag_provider() -> FeatureFlagProvider:
    settings = get_settings()
    provider = settings.feature_flag_provider.lower()
    
    if provider == "flagsmith":
        from metis.adapters.feature_flags.flagsmith import FlagsmithProvider
        return FlagsmithProvider(
            api_key=settings.flagsmith_api_key,
            env_id=settings.flagsmith_env_id,
            base_url=settings.flagsmith_base_url,
        )
    elif provider == "launchdarkly":
        from metis.adapters.feature_flags.launchdarkly import LaunchDarklyProvider
        return LaunchDarklyProvider(...)
    elif provider == "unleash":
        from metis.adapters.feature_flags.unleash import UnleashProvider
        return UnleashProvider(...)
    else:
        return StaticProvider()  # Dev default
```

### 3.5 Usage in LLM Gateway (Example)

```python
# server/metis/agent/llm.py — modified
class LLMGateway:
    def __init__(self, ..., feature_flags: FeatureFlagProvider | None = None):
        self._flags = feature_flags or await build_feature_flag_provider()
        self._context: FlagContext | None = None
    
    def set_context(self, context: FlagContext) -> None:
        self._context = context
    
    async def chat_model(self, session: AsyncSession, purpose: str) -> LLMProvider:
        # Kill switch
        if self._context and not await self._flags.is_enabled("metis.kill_switches.llm.enabled", self._context):
            raise ProviderNotConfiguredError("LLM disabled by feature flag")
        
        # Per-provider kill switch
        credentials, base_url, _ = await self._credentials(session)
        provider = self._detect_provider(base_url)
        if self._context and not await self._flags.is_enabled(f"metis.kill_switches.llm.providers.{provider}", self._context):
            raise ProviderNotConfiguredError(f"{provider} disabled by feature flag")
        
        # Model routing from JSON config
        model_config = await self._flags.get_json("metis.config.model_routing", self._context, {})
        tier_config = model_config.get("tiers", {}).get(self._context.tier, {})
        purpose_override = model_config.get("purpose_overrides", {}).get(purpose, {}).get(self._context.tier)
        model = purpose_override or tier_config.get("primary", "gpt-4o-mini")
        
        # Build model with resolved model name
        ...
```

---

## Part 4: Rollout Plan

### Phase 1: Foundation (Week 1-2)
- [ ] Add `FeatureFlagProvider` protocol + `StaticProvider` (dev)
- [ ] Add `FEATURE_FLAG_PROVIDER` to `Settings`
- [ ] Add `FlagContext` builder in `core/feature_flags/`
- [ ] Wire into `LLMGateway` for kill switch only (`llm_enabled`)

### Phase 2: Flagsmith Integration (Week 2-3)
- [ ] Implement `FlagsmithProvider` with SDK
- [ ] Add Flagsmith env vars to `.env.example` and compose
- [ ] Create Flagsmith project, environments (dev/staging/prod)
- [ ] Define flag taxonomy in Flagsmith dashboard

### Phase 3: Kill Switches (Week 3-4)
- [ ] Add per-provider LLM kill switches
- [ ] Add Exa, Sarvam, Linear, Notion kill switches
- [ ] Integrate at all call sites (LLMGateway, ExaMcpClient, STT, Integrations)
- [ ] Test failure injection in CI

### Phase 4: JSON Config + Segmentation (Week 4-6)
- [ ] Add `tier` column to `identity.workspace_settings` (migration)
- [ ] Add `beta_programs` JSON column to `identity.workspace_settings`
- [ ] Define JSON configs in Flagsmith (model_routing, rate_limits, capabilities, operational_limits)
- [ ] Integrate model routing in `LLMGateway`
- [ ] Integrate rate limits in Redis rate limiter
- [ ] Integrate capabilities in agent tools
- [ ] Integrate operational limits override in settings service

### Phase 5: Advanced (Week 6+)
- [ ] A/B testing framework for specialist prompts
- [ ] Gradual rollout for new integrations
- [ ] Audit log integration with `core.events.outbox`
- [ ] Dashboard for workspace-tier flag evaluation debugging

---

## Part 5: Testing Strategy

### 5.1 Unit Tests
- `StaticProvider` returns configured values
- `FlagContext` builder correctly extracts tier, role, beta_programs
- `LLMGateway` respects kill switches
- Model routing resolves correctly per tier/purpose

### 5.2 Integration Tests
- Flagsmith SDK connectivity (mocked)
- Flag evaluation with various context combinations
- Graceful degradation when Flagsmith unreachable (cached values)

### 5.3 E2E Tests (Playwright)
- Workspace owner sees correct capabilities per tier
- Kill switch toggled in Flagsmith → API returns disabled error within 30s
- Beta program opt-in → feature appears in UI

---

## Part 6: Operational Considerations

### 6.1 Flagsmith Deployment
| Option | Pros | Cons |
|--------|------|------|
| **Hosted (flagsmith.com)** | Zero ops, managed, SLA | Data leaves infrastructure |
| **Self-hosted (Docker/K8s)** | Data sovereignty, full control | Operational burden |
| **Hybrid** | Hosted for dev/staging, self-hosted for prod | Complexity |

**Recommendation:** Start with hosted for dev/staging; evaluate self-hosted for prod based on compliance requirements.

### 6.2 Cache Strategy
- SDK default TTL: 30 seconds
- Webhook invalidation for instant updates (Flagsmit supports)
- Fallback to poll every 60s if webhook fails
- Local in-memory cache per worker process

### 6.3 Monitoring
- Flag evaluation latency (p50, p95, p99)
- Cache hit rate
- Flagsmith API error rate
- Kill switch activation alerts (PagerDuty)

### 6.4 Rollback
- `FEATURE_FLAG_PROVIDER=static` disables all remote flags instantly
- Static provider reads from env vars for emergency overrides
- All flag keys documented in `docs/feature-flags.md`

---

## Part 7: Cost Analysis

| Component | Estimated Cost |
|-----------|----------------|
| Flagsmith Hosted (Team plan) | ~$450/month (up to 20M requests) |
| Flagsmith Self-hosted (EC2 t3.medium + RDS) | ~$80/month |
| Engineering time (6 weeks) | ~$30k-50k (internal) |
| **Total Year 1 (hosted)** | **~$35k-55k** |
| **Total Year 1 (self-hosted)** | **~$11k-31k** |

**ROI:** One prevented LLM provider outage (cost: failed runs, customer trust, support burden) pays for the service.

---

## Appendix: Flag Taxonomy Reference

### Kill Switches
```
metis.kill_switches.llm.enabled
metis.kill_switches.llm.providers.openai
metis.kill_switches.llm.providers.anthropic
metis.kill_switches.llm.providers.google
metis.kill_switches.llm.providers.local
metis.kill_switches.exa.enabled
metis.kill_switches.sarvam.enabled
metis.kill_switches.linear.enabled
metis.kill_switches.notion.enabled
```

### JSON Configs
```
metis.config.model_routing
metis.config.rate_limits
metis.config.capabilities
metis.config.operational_limits
```

### Experimental / Future
```
metis.experimental.specialist_prompts.v2
metis.experimental.scoring_rubric.v2
metis.experimental.agent_graph.v2
```

---

## Sources (Primary Codebase Files)

| File | Section |
|------|---------|
| `server/metis/core/config.py` | Settings, env vars |
| `server/metis/adapters/llm/chat.py` | LLM adapter, provider detection |
| `server/metis/agent/llm.py` | LLMGateway, per-workspace model building |
| `server/metis/adapters/mcp/exa.py` | Exa MCP client |
| `server/metis/modules/stt/service.py` | Sarvam STT service |
| `server/metis/modules/integrations/service/connections.py` | Linear/Notion MCP clients |
| `server/metis/agent/tools/export_linear.py` | Linear export tools |
| `server/metis/agent/tools/export_writes.py` | Notion export tools |
| `server/metis/modules/identity/service/provider_keys.py` | BYO key storage |
| `server/metis/modules/identity/dto/settings.py` | Workspace settings (budget, steps) |
| `server/metis/core/redis.py` | Redis connections (rate limiting) |
| `.agents/ctx/architecture.md` | System boundaries, invariants |
| `.agents/ctx/project-overview.md` | Product scope, tiers |