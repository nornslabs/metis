import type { IntegrationStatus } from "@/lib/api/queries/use-integrations";

export interface LinearItemState {
  readonly disabled: boolean;
  /** Why the item is off, or null when it is on. */
  readonly reason: string | null;
}

interface LinearItemInput {
  readonly hasPlan: boolean;
  readonly linear: IntegrationStatus;
  /** True while a run of the idea is queued, running or waiting. */
  readonly runActive: boolean;
}

/** Whether "Linear" in the Plan export menu can start an export, and why not. */
export function linearItemState({ hasPlan, linear, runActive }: LinearItemInput): LinearItemState {
  if (!hasPlan) return { disabled: true, reason: "after the plan" };
  if (linear === "not_connected") return { disabled: true, reason: "Connect Linear in Settings" };
  if (linear === "expired") return { disabled: true, reason: "Reconnect Linear in Settings" };
  if (runActive) return { disabled: true, reason: "A run is in progress" };
  return { disabled: false, reason: null };
}
