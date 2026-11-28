import type { ExportAction, ExportPreview } from "@/lib/schemas/export";

/** "new" for an item the export creates, "updated" for one it changes. */
export function actionLabel(action: ExportAction): string {
  return action === "create" ? "new" : "updated";
}

/** "3 new · 1 updated" (parts that are zero are left out; "nothing" when both are). */
export function newAndUpdated(create: number, update: number): string {
  const parts = [create > 0 ? `${create} new` : null, update > 0 ? `${update} updated` : null].filter(
    (part): part is string => part !== null,
  );
  return parts.length > 0 ? parts.join(" · ") : "nothing to save";
}

/** Labels that Linear does not have yet; null when the server could not read Linear's labels. */
export function missingLabels(preview: ExportPreview): number | null {
  if (preview.labels.items.some((label) => label.exists === null)) return null;
  return preview.labels.items.filter((label) => label.exists === false).length;
}
