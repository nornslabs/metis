import { z } from "zod";

/** Error codes the spec routes answer with (`server-context.md`, error catalog). */
export const SPEC_CONFLICT = "spec.conflict";
export const SPEC_NOT_EDITABLE = "spec.invalid_transition";
export const RUN_ENQUEUE_FAILED = "run.enqueue_failed";

/** One immutable version of an idea's spec (`SpecVersion`). */
export const specVersionSchema = z.object({
  id: z.string(),
  idea_id: z.string(),
  number: z.number().int().positive(),
  source: z.enum(["agent", "user"]),
  content_md: z.string(),
  sections: z.record(z.string(), z.string()),
  run_id: z.string().nullable(),
  created_by: z.string().nullable(),
  created_at: z.string(),
});

/** `GET /v1/ideas/{id}/spec`: the latest and the confirmed version, each `null` while there is none. */
export const specOverviewSchema = z.object({
  latest: specVersionSchema.nullable(),
  confirmed: specVersionSchema.nullable(),
});

/** `POST /v1/ideas/{id}/spec/confirm`: the confirmed version and the run it resumed, if one waited. */
export const specConfirmedSchema = z.object({
  confirmed: specVersionSchema,
  run_id: z.string().nullable(),
});

export type SpecVersion = z.infer<typeof specVersionSchema>;
export type SpecOverview = z.infer<typeof specOverviewSchema>;
export type SpecConfirmed = z.infer<typeof specConfirmedSchema>;
