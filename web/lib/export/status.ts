import { isActiveStatus, type ExportFinish, type ExportProgress } from "@/lib/events/reducer";
import type { RunStatus } from "@/lib/events/schemas";
import { safeProjectUrl, type ExportSummary } from "@/lib/schemas/export";

/** What the live run says about the export (the newest run of the idea). */
export interface LiveExport {
  readonly runId: string;
  readonly status: RunStatus;
  readonly progress: ExportProgress | null;
  readonly finish: ExportFinish | null;
  readonly error: { readonly code: string; readonly message: string } | null;
}

/** Error codes that mean the Linear connection, not the export, needs attention. */
const CONNECTION_ERROR_CODES: ReadonlySet<string> = new Set(["mcp.not_connected", "mcp.expired"]);
const EXPORT_ERROR_PREFIXES = ["export.", "mcp."] as const;
/** The one failure whose saved items are stored in the newest export job; any other failure saved nothing. */
const PARTIAL_CODE = "export.partial";

export type FailedItem = ExportSummary["failed"][number];

export type ExportStatusView =
  | { kind: "idle" }
  | { kind: "running"; progress: ExportProgress | null }
  | { kind: "succeeded"; projectUrl: string | null; created: number; updated: number; links: number }
  | {
      kind: "failed";
      /** True when the Linear connection must be renewed before a retry can work. */
      reconnect: boolean;
      message: string;
      created: number;
      updated: number;
      links: number;
      failed: readonly FailedItem[];
      projectUrl: string | null;
    };

function isExportError(code: string): boolean {
  return EXPORT_ERROR_PREFIXES.some((prefix) => code.startsWith(prefix));
}

function failure(
  summary: ExportSummary | null,
  message: string,
  reconnect: boolean,
): ExportStatusView {
  return {
    kind: "failed",
    reconnect,
    message,
    created: summary?.created ?? 0,
    updated: summary?.updated ?? 0,
    links: summary?.links ?? 0,
    failed: summary?.failed ?? [],
    projectUrl: safeProjectUrl(summary?.project_url),
  };
}

/**
 * The export block's state. A clean live finish wins; an active run with progress is running; a
 * live export failure is a failure; otherwise the stored result decides (so a reload shows it).
 */
export function exportStatusView(live: LiveExport | null, summary: ExportSummary | null): ExportStatusView {
  if (live?.finish) {
    return { kind: "succeeded", projectUrl: safeProjectUrl(live.finish.projectUrl), created: live.finish.created, updated: live.finish.updated, links: live.finish.links };
  }
  if (live && isActiveStatus(live.status) && live.progress !== null) {
    return { kind: "running", progress: live.progress };
  }
  if (live?.status === "failed" && live.error && isExportError(live.error.code)) {
    // An older job must not stand in for a run that failed before saving anything.
    const saved = live.error.code === PARTIAL_CODE ? summary : null;
    return failure(saved, live.error.message, CONNECTION_ERROR_CODES.has(live.error.code));
  }
  if (summary?.status === "succeeded") {
    return { kind: "succeeded", projectUrl: safeProjectUrl(summary.project_url), created: summary.created, updated: summary.updated, links: summary.links };
  }
  if (summary) return failure(summary, "Some items could not be saved in Linear.", false);
  return { kind: "idle" };
}

/** Whole-number percent of the export done, 0 to 100. */
export function progressPercent(progress: ExportProgress): number {
  return Math.min(100, Math.round((progress.done / Math.max(1, progress.total)) * 100));
}

const ITEM_LABELS = { project: "Project", milestone: "Milestone", issue: "Issue", links: "Links" } as const;

/** "Issue · Build the API" for the line under the bar. */
export function progressLine(progress: ExportProgress): string {
  const verb = progress.action === "create" ? "created" : "updated";
  return progress.item === "links" ? `Blocked-by links ${verb}` : `${ITEM_LABELS[progress.item]} ${verb} · ${progress.name}`;
}
