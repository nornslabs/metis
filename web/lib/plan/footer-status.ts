import type { PlanEditorState } from "@/lib/plan/plan-editor";
import type { Plan } from "@/lib/schemas/plan";

export type FooterTone = "muted" | "success" | "warning" | "destructive";

export interface FooterStatus {
  readonly text: string;
  readonly tone: FooterTone;
}

/** What the Plan footer says: the plan version, or the state of the last save. */
export function footerStatus(plan: Pick<Plan, "status" | "version">, editor: Pick<PlanEditorState, "status" | "saved">): FooterStatus {
  const version = `v${plan.version}`;
  if (plan.status === "ready") return { text: `Plan ready · ${version}`, tone: "success" };
  if (editor.status === "saving") return { text: "Saving…", tone: "warning" };
  if (editor.status === "failed") return { text: "Not saved", tone: "destructive" };
  if (editor.status === "conflict") return { text: "Plan changed elsewhere", tone: "warning" };
  if (editor.saved > 0) return { text: `Saved · ${version}`, tone: "success" };
  return { text: `Plan ${version}`, tone: "muted" };
}
