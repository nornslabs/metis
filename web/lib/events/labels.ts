import type { components } from "@/lib/api/schema";

/** Display names for graph nodes (the server's `Specialist` values); unknown nodes are title-cased. */
const NODE_LABELS: Readonly<Record<string, string>> = {
  interviewer: "Interviewer",
  researcher: "Researcher",
  scorer: "Scorer",
  advisor: "Advisor",
  architect: "Architect",
  planner: "Planner",
  integrator: "Integrator",
};

/** Display names for the idea's `Stage`. */
const STAGE_LABELS: Readonly<Record<components["schemas"]["Stage"], string>> = {
  intake: "Intake",
  interviewing: "Interviewing",
  researching: "Researching",
  scoring: "Scoring",
  advising: "Advising",
  spec_draft: "Spec draft",
  spec_confirmed: "Spec confirmed",
  planning: "Planning",
  exported: "Exported",
};

/** User-friendly display names for internal tool calls; unknown names fall back to title case. */
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

/** What a gate guards, as it reads in "skipped a question"; keyed by the server's gate names. */
const GATE_ITEM_LABELS: Readonly<Record<string, string>> = {
  interview_input: "a question",
  interview_output: "a question",
  research_input: "a search",
  advice_output: "a suggestion",
};

export function gateItemLabel(gate: string): string {
  return GATE_ITEM_LABELS[gate] ?? "an item";
}

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? titleCase(name);
}

function titleCase(value: string): string {
  const spaced = value.replaceAll("_", " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function nodeLabel(node: string): string {
  return NODE_LABELS[node] ?? titleCase(node);
}

export function stageLabel(stage: string): string {
  return (STAGE_LABELS as Readonly<Record<string, string>>)[stage] ?? titleCase(stage);
}
