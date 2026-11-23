# PRD: Fix SHIP-281 / #69 — Hide Internal Tool Names During Research

## Problem Statement

During the research process, internal tool calls like `recall_memory`, `ask_user`, `kb_lookup`, and `save_research_item` are displayed with technical names in the UI. These names are not user-friendly and should be hidden or replaced with simple, readable labels.

**Linear Issue**: [SHIP-281](https://linear.app/heimdallabs/issue/SHIP-281/hide-internal-tool-names-during-research)
**GitHub Issue**: [#69](https://github.com/nornslabs/metis/issues/69)

### Steps to Reproduce
1. Start an idea that triggers research
2. Watch the step list during the Researcher step
3. Observe: internal tool names like `recall_memory`, `kb_lookup`, `save_research_item` appear as technical text under the step

### Expected Behavior
Show clean, user-friendly names instead of internal tool names, or hide these technical details completely.

---

## Root Cause Analysis

Two places display raw internal tool names:

### 1. `web/components/chat/step-list.tsx:52`
```tsx
{step.tools.length > 0 ? (
  <span className="pl-5 font-mono text-meta text-muted-foreground">{step.tools.join(" · ")}</span>
) : null}
```
This joins raw tool names (e.g. `recall_memory · kb_lookup · save_research_item`) and shows them under each step row.

### 2. `web/lib/events/activity.ts:19`
```tsx
const tool = running.tools.at(-1);
const label = running.node === RESEARCHER_NODE ? "Researching…" : `${nodeLabel(running.node)}…`;
return tool ? `${label} ${tool}` : label;
```
This appends the latest raw tool name to the activity shimmer (e.g. "Researching… web_search_exa").

### Tool names collected from

The tools come from server-side `tool_call` events, reduced into `RunStep.tools` in `reducer.ts` via `addTool()`. Values observed include: `web_search`, `web_search_exa`, `fetch`, `ask`, `ask_user`, `recall_memory`, `kb_lookup`, `save_research_item`.

---

## Solution Strategy

Create a tool-name display mapping that converts internal tool names to user-friendly labels, applied in both `step-list.tsx` and `activity.ts`. Tools without a mapping fall back to a title-cased version of the name (underscores → spaces, first letter capitalized) rather than showing the raw snake_case name.

### Tool name mapping (config-driven in `labels.ts`)

| Internal name | User-friendly label |
|---------------|---------------------|
| `web_search_exa` | Web search |
| `web_search` | Web search |
| `fetch` | Fetch page |
| `ask_user` | Ask question |
| `ask` | Ask question |
| `recall_memory` | Recall memory |
| `kb_lookup` | Knowledge base |
| `save_research_item` | Save finding |

Any unknown tool name → `titleCase(name)` (e.g. `my_tool` → "My tool").

---

## Detailed Requirements

### FR-1: Tool names shown as user-friendly labels
**Requirement**: Each tool name displayed in the step list and activity shimmer must use a user-friendly label instead of the raw internal name.

**Acceptance Criteria**:
- `recall_memory` → "Recall memory"
- `kb_lookup` → "Knowledge base"
- `save_research_item` → "Save finding"
- `web_search_exa` / `web_search` → "Web search"
- `ask_user` / `ask` → "Ask question"
- `fetch` → "Fetch page"
- Unknown tools → title-cased (e.g. `my_tool` → "My tool")

### FR-2: Single source of truth for mapping
**Requirement**: The mapping lives in one place (`labels.ts`) and is reused by both `step-list.tsx` and `activity.ts`.

**Acceptance Criteria**:
- `toolLabel(name: string): string` exported from `labels.ts`
- Both `step-list.tsx` and `activity.ts` import and use it

### FR-3: No raw snake_case names visible
**Requirement**: No internal snake_case tool name should be visible to the user anywhere in the research UI.

**Acceptance Criteria**:
- `step-list.tsx` uses `toolLabel()` for each tool in the join
- `activity.ts` uses `toolLabel()` for the latest tool
- Existing tests updated to expect friendly labels

---

## Technical Implementation Plan

### File 1: `web/lib/events/labels.ts`
Add a `TOOL_LABELS` record and `toolLabel()` function:

```ts
const TOOL_LABELS: Readonly<Record<string, string>> = {
  web_search_exa: "Web search",
  web_search: "Web search",
  fetch: "Fetch page",
  ask_user: "Ask question",
  ask: "Ask question",
  recall_memory: "Recall memory",
  kb_lookup: "Knowledge base",
  save_research_item: "Save finding",
};

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? titleCase(name);
}
```

### File 2: `web/components/chat/step-list.tsx`
Replace `step.tools.join(" · ")` with `step.tools.map(toolLabel).join(" · ")`.

### File 3: `web/lib/events/activity.ts`
Replace `${tool}` with `${toolLabel(tool)}` in `runActivity`.

### Verification
1. **Manual test**: Open an idea with research → watch step list during Researcher step → confirm friendly labels
2. **Unit tests**: Update `activity.test.ts` and `reducer.test.ts` expectations for friendly labels
3. **E2E tests**: Update `interview-research.spec.ts` and `idea-chat.spec.ts` expectations
4. **Lint**: `pnpm eslint` passes
5. **Build**: `pnpm next build` passes

---

## Acceptance Criteria (Definition of Done)

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| 1 | Tool names show user-friendly labels instead of snake_case | Manual test + E2E |
| 2 | Mapping is centralized in `labels.ts` | Code review |
| 3 | Both step list and activity shimmer use `toolLabel()` | Code review |
| 4 | Unknown tools fall back to title case | Unit test |
| 5 | All existing tests pass | `pnpm test` / `pnpm e2e` |

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| New tool names added on server without mapping | Medium | Low | Fallback to `titleCase()` ensures no raw snake_case |
| E2E tests assert raw tool names | Medium | Low | Update test expectations to friendly labels |

---

## Appendix: Code Pointers

| Component | Path | Relevance |
|-----------|------|-----------|
| Tool label mapping (new) | `web/lib/events/labels.ts` | Add `TOOL_LABELS` + `toolLabel()` |
| Step list (display) | `web/components/chat/step-list.tsx:52` | Shows `step.tools.join(" · ")` |
| Activity shimmer (display) | `web/lib/events/activity.ts:19` | Shows latest tool name |
| Labels (node/stage names) | `web/lib/events/labels.ts` | Existing `NODE_LABELS` pattern to follow |
| Reducer (collects tools) | `web/lib/events/reducer.ts:121` | `addTool()` collects names — no change needed |
| Activity tests | `web/lib/events/activity.test.ts` | Update expectations |
| Reducer tests | `web/lib/events/reducer.test.ts` | Update expectations |
| E2E interview-research | `web/e2e/interview-research.spec.ts` | Update expectations |
| E2E idea-chat | `web/e2e/idea-chat.spec.ts` | Update expectations |