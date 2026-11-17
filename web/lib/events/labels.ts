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
