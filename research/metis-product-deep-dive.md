# Metis: Product Deep Dive

**Date:** 2026-11-24
**Status:** Living document — updated as product evolves
**Audience:** Engineering, Product, Design, Investors

---

## What Is Metis?

**Metis** is an **agentic planning application** that turns a raw idea (software or non-software) into a researched, scored, and buildable plan — in one session.

> **Tagline:** "From 'I have an idea' to 'Here's the Linear project with milestones and tasks' — without the weeks of research, scoring debates, and spec-writing."

### The Core Insight

Founders and solo hackers **don't fail because they can't code**. They fail because:
1. **They build the wrong thing** — no validated problem, no market, no differentiation
2. **They skip the hard thinking** — interview yourself? Research competitors? Score objectively? Nobody does it consistently
3. **They can't translate insight to execution** — even with a good score, turning it into a spec, then phases, then Linear issues is a separate skill

Metis automates the **entire pre-execution loop**: Interview → Research → Score → Spec → Plan → Export.

---

## The Problem Space (Real, Not Theoretical)

### Problem 1: The "Idea Validation Gap"

| Current Approach | Reality |
|-----------------|---------|
| "I'll talk to 10 users" | Talks to 2 friends who say "cool idea" |
| "I'll research competitors" | Googles for 20 minutes, finds 3, misses the 10 that matter |
| "I'll build an MVP" | Spends 3 months building something nobody wants |
| "I'll use a framework" | Fills out a Lean Canvas once, never revisits |

**Result:** 90%+ of ideas die in the valley between "I have an idea" and "I have a validated plan worth building."

### Problem 2: The "Scoring Subjectivity Trap"

| What Founders Do | What They Need |
|-----------------|----------------|
| Gut feel: "This feels like a 8/10" | Fixed rubric: Problem 25%, Uniqueness 25%, Market 15%, Value 15%, Feasibility 10%, Timing 10% |
| "My idea is unique" | Evidence: 12 competitors found, overlap scores, pricing comparison |
| "Market is huge" | Data: TAM/SAM/SOM with sources, demand signals, trend analysis |
| "I can build this" | Feasibility: Technical complexity, team skills, dependency risk |

**Result:** Founders overestimate by 30-50 points. Metis forces evidence-based scoring.

### Problem 3: The "Spec-to-Execution Chasm"

| Artifact | Typical State | Metis Output |
|----------|---------------|--------------|
| Spec | "Build a todo app with AI" | 15-section HLD: architecture, data model, API contracts, security, phases |
| Plan | "Phase 1: Build it" | 8 phases, 47 tasks, dependencies, Fibonacci points, Linear-ready |
| Export | Manual copy-paste to Linear | One click: Project + Milestones + Issues with blocked-by links |

**Result:** Weeks of planning compressed to minutes. Re-runnable when market changes.

---

## How Metis Solves These Problems

### Flow Overview

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────────┐    ┌────────────┐
│   IDEA      │───▶│  ADAPTIVE        │───▶│   EXA       │───▶│   FIXED     │───▶│   SPEC      │───▶│  LINEAR    │
│   INPUT     │    │  INTERVIEW       │    │   RESEARCH  │    │   RUBRIC    │    │   & PLAN    │    │  EXPORT    │
└─────────────┘    └──────────────────┘    └─────────────┘    └─────────────┘    └──────────────┘    └────────────┘
      │                   │                      │                  │                  │                 │
      ▼                   ▼                      ▼                  ▼                  ▼                 ▼
  Title +           5-15 questions,          20+ sources,       6 params,          Versioned,       Project +
  raw text          skips known answers      competitors,       evidence-based,    editable,        Milestones +
  + kind            from memory              market facts,      <55 = adviser      phases, tasks    Issues w/
                                                    mode                                 w/ deps       blocked-by
```

### Stage 1: Adaptive Interview (The "Why" Engine)

**What it does:** Conducts a structured interview covering 4 topics:
1. **Problem Severity** — Why does this need to exist? Who feels the pain acutely?
2. **Solution Viability** — Why will this work? What's the insight?
3. **Commercial Logic** — Who pays? How much? How often?
4. **Feasibility** — What's hard? What dependencies? What could kill it?

**Adaptive logic:** If user memory (previous runs, saved context) already covers a topic, Metis skips it. New founders get full interview; serial founders get 3 questions.

**Output:** `InterviewBrief` — structured findings per topic, confidence scores, gaps identified.

### Stage 2: Exa Research (The "Evidence" Engine)

**What it does:** Uses Exa (AI-native search) to find:
- **Direct competitors** — Same problem, same solution approach
- **Adjacent competitors** — Same problem, different approach
- **Market facts** — TAM, growth rates, funding trends, user sentiment
- **Trends** — Why now? Technology shifts, regulation, behavior changes
- **Risks** — Technical barriers, regulatory, competitive moats

**Knowledge Base:** Every competitor found is saved to a **workspace-shared KB** with embeddings. Future runs on similar ideas instantly retrieve prior research — compounding value.

**Graceful degradation:** No Exa key? Research skipped, run completes, user notified. Add key later → re-run does research.

### Stage 3: Fixed-Rubric Scoring (The "Objectivity" Engine)

**Rubric (immutable, versioned):**

| Parameter | Weight | What It Measures |
|-----------|--------|------------------|
| Problem Severity | 25% | Pain intensity, frequency, urgency, willingness to pay |
| Uniqueness | 25% | Differentiation vs competitors, defensibility, IP potential |
| Market Demand | 15% | TAM/SAM/SOM evidence, search volume, hiring trends, funding |
| Value Capture | 15% | Pricing power, retention potential, expansion revenue, margins |
| Feasibility | 10% | Technical complexity, team fit, dependency risk, time to MVP |
| Timing | 10% | Why now? Tailwinds, headwinds, window of opportunity |

**Output per parameter:**
- Score (0-100)
- **Reason** — 2-3 sentence explanation
- **Evidence** — Links to research sources (Exa URLs, KB entries)
- **Confidence** — 0-1 (how sure the model is)

**Bands:**
- **75+** → "Build it" — Green light, proceed to spec
- **55-74** → "Promising" — Proceed but address specific gaps
- **<55** → **Adviser Mode** — Pivot suggestions, gap analysis, revise & rescore

**Adviser Mode (unique):** Instead of "your idea is bad," Metis says:
> "Score: 42. Problem severity is strong (78) but Uniqueness is 22 — 3 direct competitors with same approach. Feasibility is 35 — needs ML expertise you don't have. Suggestions: 1) Pivot to [adjacent problem], 2) Partner with [type of co-founder], 3) Start with [smaller scope]. Revise and rescore."

### Stage 4: Spec & Plan (The "Execution" Engine)

**Spec Generation (Architect specialist):**
- 15-section HLD: Context, Requirements, Architecture, Data Model, API, Security, Infra, Risks, etc.
- Saved to Notion (software ideas) — versioned, collaborative
- User edits → Metis regenerates affected sections

**Planning (Planner + Integrator specialists):**
- User configures phases (or accepts proposal)
- Metis breaks phases into tasks with:
  - Title, description, acceptance criteria
  - Fibonacci points (1, 2, 3, 5, 8, 13)
  - **Dependencies** (blocked-by) — critical path visible
  - Labels (frontend, backend, infra, research, etc.)
  - Assignee suggestions (based on workspace members)

**Linear Export (Integrator specialist):**
- One Linear project per idea
- Milestones = phases
- Issues = tasks with blocked-by links
- **Rebalance (future):** Re-run export → creates new issues, updates changed, cancels obsolete, keeps done

### Stage 5: Market Watch (The "Live" Engine)

**Weekly per-idea (toggleable):**
1. Re-run Exa research (incremental — only new sources)
2. Re-score with new evidence
3. If score changes >5 points or new competitors found:
   - In-app alert
   - Score history chart
   - Suggested spec/plan changes
   - One-click Linear rebalance

**Result:** Your plan doesn't rot. It evolves with the market.

---

## Technical Architecture (Why It Works)

### Multi-Tenant, BYO Keys, Zero Lock-in

| Concern | Metis Approach |
|---------|----------------|
| **Data isolation** | Postgres RLS — every table has `workspace_id`, enforced at DB level |
| **LLM costs** | Bring Your Own Key — user pays their provider directly |
| **Provider lock-in** | OpenAI-compatible interface — works with OpenAI, Anthropic, Google, Ollama, custom proxies |
| **Research lock-in** | Exa via MCP — standard protocol, swappable |
| **Export lock-in** | Linear/Notion via MCP — user owns their data in those tools |
| **Portability** | Markdown export for everything — spec, plan, score, research |

### Agent Architecture (LangGraph)

```
Supervisor (pure function router)
    │
    ├── Interviewer  ──▶ Asks questions, saves brief
    ├── Researcher   ──▶ Exa tools + KB tools, saves snapshot
    ├── Scorer       ──▶ Rubric evaluation, structured output
    ├── Advisor      ──▶ Gap analysis, pivot suggestions (if <55)
    ├── Architect    ──▶ HLD spec generation
    ├── Planner      ──▶ Phase/task breakdown with dependencies
    └── Integrator   ──▶ Linear/Notion MCP export
```

**Key properties:**
- **Checkpointed** — Every step saved to Postgres; worker crash → resume from last step
- **Interrupt-driven** — User decisions (advice, phase review, export approval) via `interrupt()` / `Command(resume=...)`
- **Budgeted** — Per-run token budget (`run_budget_usd`), step limit (`max_steps`), recorded per-call in `ideas.llm_usage`
- **Observable** — Langfuse tracing, SSE live events to web UI

### Adapter Pattern (Swappable Everything)

```
┌─────────────────────────────────────────────────────────────┐
│                      METIS CORE                              │
├─────────────────────────────────────────────────────────────┤
│  LLMProvider Protocol    │  Embedder Protocol               │
│  ResearchPort Protocol   │  OutputPort Protocol             │
│  InputPort Protocol      │  MCPClient Protocol              │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ OpenAI        │    │ Exa MCP       │    │ Linear MCP    │
│ Anthropic     │    │ (research)    │    │ (export)      │
│ Google        │    │               │    │ Notion MCP    │
│ Ollama        │    │ Sarvam STT    │    │ (future)      │
│ Custom Proxy  │    │ (voice)       │    │               │
└───────────────┘    └───────────────┘    └───────────────┘
```

**Adding a new provider = one adapter file implementing the protocol.** No core changes.

---

## Business Model & Go-to-Market

### Current (Hackathon MVP)
- **Free** — No hosted keys, no paid plans
- **BYO LLM key** (required) + **BYO Exa key** (optional)
- **Target:** Solo hackers, indie founders, YC/Winter batch companies
- **Distribution:** Open source, Product Hunt, founder communities

### Near Term (Post-MVP)
| Tier | Price | Includes |
|------|-------|----------|
| Free | $0 | 1 workspace, gpt-4o-mini, 5 runs/mo, basic export |
| Personal | $20/mo | Unlimited runs, gpt-4o, voice, code exec, market watch |
| Team | $50/mo/seat | Shared KB, SSO, custom rubrics, priority support |
| Enterprise | Custom | Dedicated infra, SLA, audit log, custom integrations |

### Differentiation vs Alternatives

| Tool | Does Interview? | Does Research? | Fixed Rubric? | Spec → Linear? | Live Scores? |
|------|----------------|----------------|---------------|----------------|--------------|
| **Metis** | ✅ Adaptive | ✅ Exa + KB | ✅ Immutable | ✅ One-click | ✅ Weekly |
| ChatGPT | Manual | Manual | ❌ | Manual | ❌ |
| Notion AI | ❌ | ❌ | ❌ | Manual | ❌ |
| Linear | ❌ | ❌ | ❌ | Native | ❌ |
| Productboard | ❌ | ❌ | Configurable | ❌ | ❌ |
| Aha! | ❌ | ❌ | Configurable | ❌ | ❌ |
| Custom scripts | Maybe | Maybe | Maybe | Maybe | ❌ |

**Metis = The only tool that does the FULL loop automatically.**

---

## Success Metrics (Product)

### Activation
- **Time to first score** < 10 minutes (idea → interview → research → score)
- **Interview completion rate** > 80% (adaptive = shorter for returning users)
- **Research skip rate** < 20% (Exa key adoption)

### Engagement
- **Runs per workspace/month** > 3 (serial ideation)
- **Re-score rate** > 40% (market watch or manual re-check)
- **Export rate** > 60% of scored ideas (score ≥ 55)

### Retention
- **Monthly active workspaces** growing 20% MoM
- **Ideas exported to Linear** → issues created → issues closed (track through Linear webhook)
- **Market watch enabled** > 70% of exported ideas

### Quality
- **Score calibration** — Founder's post-launch outcome vs Metis score (long-term)
- **Competitor KB hit rate** — % of runs using KB vs fresh Exa (target > 60%)
- **Adviser mode conversion** — % of <55 scores that revise and reach ≥55 (target > 30%)

---

## Roadmap (High-Level)

### Phase 1: Core Loop Done (Current)
- [x] Auth, workspaces, BYO keys
- [x] Interview → Research → Score → Adviser
- [x] Spec generation, phase planning
- [x] Linear export (MCP)
- [ ] Notion export (HLD)
- [ ] Market watch (scheduled re-score)
- [ ] Rebalance (Linear update on re-export)

### Phase 2: Platform Features
- [ ] Learning agent (per-user memory, shared KB calibration)
- [ ] Public shareable score cards
- [ ] GitHub Issues export (alongside Linear)
- [ ] Slack/Discord bot for interview input
- [ ] CLI for headless runs

### Phase 3: Enterprise & Ecosystem
- [ ] SSO (SAML/OIDC)
- [ ] Audit log, compliance reports
- [ ] Custom rubrics per workspace
- [ ] Metis as MCP server (other agents can call it)
- [ ] Marketplace: community rubrics, specialist prompts, integrations

---

## Why This Matters Now

### Macro Tailwinds
1. **LLM costs dropping 10x/year** — Agentic workflows becoming economically viable
2. **Founder tooling gap** — Plenty of code gen (Cursor, Copilot), zero pre-code validation
3. **MCP standardization** — Universal protocol for tools = pluggable integrations
4. **Solo founder renaissance** — AI enables 1-person companies; they need planning leverage

### Metis Timing
- **Not too early** — LLMs reliable enough for structured output (JSON modes, function calling)
- **Not too late** — No dominant player in "agentic planning" category
- **Right abstraction** — MCP makes integrations maintainable; adapter pattern makes providers swappable

---

## Appendix: Key Files for Engineers

| Area | Entry Points |
|------|--------------|
| **Agent Graph** | `server/metis/agent/graph.py`, `server/metis/agent/supervisor.py` |
| **Specialists** | `server/metis/agent/specialists/` (stubs + real) |
| **Tools** | `server/metis/agent/tools/` (Exa, Linear, Interview, Scoring, etc.) |
| **LLM Gateway** | `server/metis/agent/llm.py` |
| **Adapters** | `server/metis/adapters/llm/`, `server/metis/adapters/mcp/` |
| **Modules** | `server/metis/modules/` (auth, identity, ideas, research, scoring, planning, integrations, stt) |
| **Web UI** | `web/components/chat/`, `web/components/panel/`, `web/components/settings/` |
| **API** | `server/metis/entrypoints/api.py` + module controllers |
| **Config** | `server/metis/core/config.py` |

---

## Closing Thought

> **Metis doesn't replace founder judgment. It forces the judgment to happen explicitly, evidence-based, and recorded — before the expensive part (building) begins.**

Every successful company started as an idea that survived this loop. Metis just makes the loop fast, rigorous, and repeatable.