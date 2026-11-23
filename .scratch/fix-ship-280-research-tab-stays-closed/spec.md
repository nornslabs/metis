# PRD: Fix SHIP-280 — Research Tab Opens Automatically After User Closes It

## Problem Statement

When a user closes the Research tab/panel and enters new input, the Research panel reopens automatically.

**Linear Issue**: [SHIP-280](https://linear.app/heimdallabs/issue/SHIP-280/research-tab-opens-automatically-after-user-closes-it)
**GitHub Issue**: [#68](https://github.com/nornslabs/metis/issues/68)

### Steps to Reproduce
1. Open an idea with completed research
2. Close the Research `<details>` panel (click the summary to collapse it)
3. Enter new input (send a message / start a new run)
4. Observe: the Research panel reopens automatically

### Expected Behavior
The Research panel should remain closed after the user manually closes it, until the user explicitly opens it again.

---

## Root Cause Analysis

### File: `web/components/research/research-panel.tsx:25`

```tsx
<details open className="group border">
```

The `open` attribute is set unconditionally on every render. This means:

1. React re-renders the component whenever run state changes (new events, new research data, etc.)
2. Each render re-applies `open`, forcing the `<details>` element to open
3. Even if the user collapses the panel, the next render re-expands it

### Why It Happens on New Input

When the user enters new input:
- A new run starts or the existing run produces new events
- `RunConversation` re-renders → `ResearchSection` re-renders → `ResearchPanel` re-renders
- `<details open>` forces the panel open again

### Fix

Replace the unconditional `open` attribute with React-controlled state:

- Track `isOpen` in React state, initialized to `true` (panel starts open by default)
- Use `onToggle` to sync state when the user clicks the summary
- Pass `open={isOpen}` so React controls the attribute (no forced reopen on render)
- Once `isOpen` is `false`, re-renders won't force it back open

---

## Detailed Requirements

### FR-1: Research Panel Respects User Close Action
**Requirement**: Once the user closes the Research panel, it must stay closed across re-renders and new input.

**Acceptance Criteria**:
- Closing the panel (clicking the summary to collapse) sets `isOpen = false`
- Subsequent renders do not force `open` back to `true`
- Panel only reopens when the user explicitly clicks the summary again

### FR-2: Panel Starts Open by Default
**Requirement**: On first render for a given idea/run, the Research panel is open (current behavior preserved for new content).

**Acceptance Criteria**:
- `isOpen` initializes to `true`
- First-time viewers see the research panel open

### FR-3: No Flash of Closed-then-Open
**Requirement**: The panel must not briefly open and then close (or vice versa) during render transitions.

**Acceptance Criteria**:
- Controlled `open={isOpen}` with state only changing via `onToggle`
- No `defaultOpen` conflicting with controlled `open`

---

## Technical Implementation Plan

### Single File Change: `web/components/research/research-panel.tsx`

1. Add `useState` import from React
2. Add `isOpen` state initialized to `true`
3. Replace `<details open>` with `<details open={isOpen} onToggle={...}>`
4. `onToggle` reads `event.target.open` to set state (handles programmatic + user clicks)

```tsx
import { useState } from "react";

// ...

export function ResearchPanel({ view }: { view: ResearchView }) {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <details
      open={isOpen}
      onToggle={(event) => setIsOpen((event.target as HTMLDetailsElement).open)}
      className="group border"
    >
      ...
    </details>
  );
}
```

### Verification

1. **Manual test**: Open idea with research → close panel → send new message → panel stays closed
2. **E2E test**: Add to `web/e2e/interview-research.spec.ts` or new spec
3. **Lint**: `pnpm eslint` passes
4. **Build**: `pnpm next build` passes

---

## Acceptance Criteria (Definition of Done)

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| 1 | Closing Research panel keeps it closed after new input | Manual test + E2E |
| 2 | Panel starts open on first view | Manual test |
| 3 | User can reopen panel after closing | Manual test |
| 4 | No console errors during open/close toggling | Manual + CI |
| 5 | All existing tests pass | `pnpm test` / `pnpm e2e` |

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Controlled `open` conflicts with native `<details>` behavior | Low | Low | `onToggle` reads actual `event.target.open`, keeping state in sync |
| Panel state resets on navigation to different idea | Low | Low | Each `ResearchPanel` instance has its own state; new idea = new component = fresh `true` state (desired) |

---

## Out of Scope
- Persisting closed state across page reloads (localStorage)
- Global "research always closed" preference
- Animation on open/close

---

## Appendix: Code Pointers

| Component | Path | Relevance |
|-----------|------|-----------|
| Research panel (primary fix) | `web/components/research/research-panel.tsx` | `<details open>` — root cause |
| Research section (parent) | `web/components/research/research-section.tsx` | Renders `ResearchPanel` |
| Run conversation (caller) | `web/components/chat/run-conversation.tsx:193` | Passes `researchStarted` prop |