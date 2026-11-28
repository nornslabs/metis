import { z } from "zod";

/** What the Linear export does with one item: make it, or change the one it made before. */
export const exportActionSchema = z.enum(["create", "update"]);
export type ExportAction = z.infer<typeof exportActionSchema>;

/** The kinds of item the export saves, in the order it saves them. */
export const exportItemSchema = z.enum(["project", "milestone", "issue", "links", "hld"]);
export type ExportItem = z.infer<typeof exportItemSchema>;

const countsSchema = z.object({
  total: z.number().int().nonnegative(),
  create: z.number().int().nonnegative(),
  update: z.number().int().nonnegative(),
});

/** The preview the `export_approval` interrupt carries (`agent/tools/export_preview.py`). */
export const exportPreviewSchema = z.object({
  team: z.object({ id: z.string(), name: z.string() }),
  plan_version: z.number().int().nonnegative(),
  project: z.object({ name: z.string(), action: exportActionSchema }),
  milestones: countsSchema.extend({
    items: z.array(z.object({ name: z.string(), action: exportActionSchema })),
  }),
  issues: countsSchema,
  blocked_by_links: z.number().int().nonnegative(),
  labels: z.object({
    total: z.number().int().nonnegative(),
    items: z.array(z.object({ name: z.string(), exists: z.boolean().nullable() })),
  }),
});
export type ExportPreview = z.infer<typeof exportPreviewSchema>;

/** What the answer of `POST /v1/runs/{id}/resume` must carry for each export interrupt. */
export const teamChoiceSchema = z.object({ team_id: z.string().min(1) });
export const exportDecisionSchema = z.object({ approved: z.boolean() });

const failedItemSchema = z.object({ kind: z.string(), name: z.string(), reason: z.string() });

/** The newest finished export of one idea (`GET /v1/exports/summaries`). */
export const exportSummarySchema = z.object({
  idea_id: z.string(),
  status: z.enum(["succeeded", "partial", "failed"]),
  project_url: z.string().nullable(),
  created: z.number().int().nonnegative(),
  updated: z.number().int().nonnegative(),
  links: z.number().int().nonnegative(),
  failed: z.array(failedItemSchema),
  finished_at: z.string().nullable(),
});
export type ExportSummary = z.infer<typeof exportSummarySchema>;

/** A Linear link is shown only when it is a plain `https:` URL. */
export function safeProjectUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}
