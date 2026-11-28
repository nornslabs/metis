import { z } from "zod";

import {
  exportActionSchema,
  exportItemSchema,
  exportPreviewSchema,
  type ExportPreview,
} from "@/lib/schemas/export";
import { reviewedPhaseSchema, type ReviewedPhase } from "@/lib/schemas/plan";

/**
 * Zod schemas for the run events the server streams (`core.events.RunEventType`). Each SSE frame's
 * `data` is the envelope `{run_id, type, data, ts}`; the payload shape depends on `type`.
 */

export const RUN_EVENT_TYPES = [
  "run_status",
  "node_started",
  "node_finished",
  "tool_call",
  "token",
  "interrupt",
  "notice",
  "score",
  "export_progress",
  "export_finished",
  "gate",
] as const;

export type RunEventType = (typeof RUN_EVENT_TYPES)[number];

export const runStatusSchema = z.enum([
  "queued",
  "running",
  "awaiting_user",
  "succeeded",
  "failed",
  "cancelled",
]);

export type RunStatus = z.infer<typeof runStatusSchema>;

export const runErrorSchema = z.object({ code: z.string(), message: z.string() });

export type RunError = z.infer<typeof runErrorSchema>;

const scoreBandSchema = z.enum(["build", "promising", "advise"]);

/** One answer the user can pick for a question; `id` is what the resume call sends. */
export type QuestionOption = {
  readonly id: string;
  readonly label: string;
  readonly detail?: string;
  readonly recommended: boolean;
};

/**
 * A question the run waits on. A plain question has only `text`; one with `options` is answered
 * with a pick (`multi`: several) or, when `allowFreeText`, with typed text. `index` and `total` give
 * "Question n of m".
 */
export type QuestionInterrupt = {
  kind: "question";
  text: string;
  options?: readonly QuestionOption[];
  multi?: boolean;
  allowFreeText?: boolean;
  index?: number;
  total?: number;
};

/**
 * A question, approval or advice decision the run waits on, reduced to what the page shows. For an
 * advice decision `text` is the score run's id, so two decisions are never taken for the same one.
 */
export type ApprovalInterrupt = { kind: "approval"; text: string; details?: string };
export type AdviceInterrupt = {
  kind: "advice_decision";
  text: string;
  scoreRunId: string;
  total: number;
  band: z.infer<typeof scoreBandSchema>;
};
/** The run paused for the user to confirm the spec; `text` is the draft's version id. */
export type SpecReviewInterrupt = { kind: "spec_review"; text: string; specVersionId: string; number: number };
/** The run paused for the user to review the Planner's phases; `text` is their names, so a new proposal is a new pause. */
export type PhaseReviewInterrupt = { kind: "phase_review"; text: string; phases: readonly ReviewedPhase[] };
/** One Linear team the export may use. */
export type ExportTeamChoice = { readonly id: string; readonly name: string; readonly key: string };
/** The export waits for a Linear team; `savedTeamId` is set when the saved team is no longer in Linear. `text` is the team ids. */
export type ChooseTeamInterrupt = {
  kind: "choose_team";
  text: string;
  teams: readonly ExportTeamChoice[];
  savedTeamId: string | null;
};
/** The export waits for approval of `preview`; `text` is the plan version, so a new preview is a new pause. */
export type ExportApprovalInterrupt = { kind: "export_approval"; text: string; preview: ExportPreview };
/** The two pauses of the Linear export. */
export type ExportInterrupt = ChooseTeamInterrupt | ExportApprovalInterrupt;
export type RunInterrupt =
  | QuestionInterrupt
  | ApprovalInterrupt
  | AdviceInterrupt
  | SpecReviewInterrupt
  | PhaseReviewInterrupt
  | ChooseTeamInterrupt
  | ExportApprovalInterrupt;

const questionOptionSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  detail: z.string().nullish(),
  recommended: z.boolean().default(false),
});

const questionPayloadSchema = z.object({
  type: z.literal("question"),
  question: z.string(),
  multi: z.boolean().optional(),
  options: z.array(questionOptionSchema).optional(),
  allow_free_text: z.boolean().optional(),
  index: z.number().int().positive().optional(),
  total: z.number().int().positive().optional(),
});

type QuestionPayload = z.infer<typeof questionPayloadSchema>;

/** Only the fields the server sent: a plain `{type, question}` stays `{kind, text}`. */
function toQuestionInterrupt(value: QuestionPayload): QuestionInterrupt {
  return {
    kind: "question",
    text: value.question,
    ...(value.options && {
      options: value.options.map(({ id, label, detail, recommended }) => ({
        id,
        label,
        recommended,
        ...(detail ? { detail } : {}),
      })),
    }),
    ...(value.multi !== undefined && { multi: value.multi }),
    ...(value.allow_free_text !== undefined && { allowFreeText: value.allow_free_text }),
    ...(value.index !== undefined && { index: value.index }),
    ...(value.total !== undefined && { total: value.total }),
  };
}

export const interruptSchema = z
  .union([
    questionPayloadSchema,
    z.object({ type: z.literal("approval"), action: z.string(), details: z.unknown().optional() }),
    z.object({
      type: z.literal("advice_decision"),
      score_run_id: z.string(),
      total: z.number(),
      band: scoreBandSchema,
    }),
    z.object({ type: z.literal("spec_review"), spec_version_id: z.string(), number: z.number().int().positive() }),
    z.object({ type: z.literal("phase_review"), phases: z.array(reviewedPhaseSchema).min(1) }),
    z.object({
      type: z.literal("choose_team"),
      teams: z.array(z.object({ id: z.string().min(1), name: z.string(), key: z.string() })).min(1),
      saved_team_id: z.string().nullish(),
    }),
    z.object({ type: z.literal("export_approval"), preview: exportPreviewSchema }),
  ])
  .transform((value): RunInterrupt => {
    if (value.type === "question") return toQuestionInterrupt(value);
    if (value.type === "advice_decision") {
      return { kind: "advice_decision", text: value.score_run_id, scoreRunId: value.score_run_id, total: value.total, band: value.band };
    }
    if (value.type === "spec_review") {
      return { kind: "spec_review", text: value.spec_version_id, specVersionId: value.spec_version_id, number: value.number };
    }
    if (value.type === "phase_review") {
      return { kind: "phase_review", text: JSON.stringify(value.phases), phases: value.phases };
    }
    if (value.type === "choose_team") {
      return {
        kind: "choose_team",
        text: value.teams.map((team) => team.id).join(","),
        teams: value.teams,
        savedTeamId: value.saved_team_id ?? null,
      };
    }
    if (value.type === "export_approval") {
      return { kind: "export_approval", text: String(value.preview.plan_version), preview: value.preview };
    }
    const details = typeof value.details === "string" && value.details.trim() !== "" ? value.details : undefined;
    return { kind: "approval", text: value.action, ...(details && { details }) };
  });

const nodeSchema = z.object({ node: z.string() });

export const gateDecisionSchema = z.enum(["passed", "retried", "skipped"]);

export type GateDecision = z.infer<typeof gateDecisionSchema>;

const payloadSchemas = {
  run_status: z
    .object({ status: runStatusSchema, error: runErrorSchema.optional() })
    .transform(({ status, error }) => ({ type: "run_status" as const, status, ...(error && { error }) })),
  node_started: nodeSchema.transform(({ node }) => ({ type: "node_started" as const, node })),
  node_finished: nodeSchema.transform(({ node }) => ({ type: "node_finished" as const, node })),
  tool_call: z
    .object({ node: z.string(), name: z.string() })
    .transform(({ node, name }) => ({ type: "tool_call" as const, node, name })),
  token: z
    .object({ node: z.string(), text: z.string() })
    .transform(({ node, text }) => ({ type: "token" as const, node, text })),
  interrupt: interruptSchema.transform((interrupt) => ({ type: "interrupt" as const, interrupt })),
  notice: z
    .object({ code: z.string(), text: z.string() })
    .transform(({ code, text }) => ({ type: "notice" as const, code, text })),
  score: z
    .object({ score_run_id: z.string(), total: z.number(), band: scoreBandSchema })
    .transform(({ score_run_id, total, band }) => ({ type: "score" as const, scoreRunId: score_run_id, total, band })),
  export_progress: z
    .object({
      item: exportItemSchema,
      name: z.string(),
      action: exportActionSchema,
      done: z.number().int().nonnegative(),
      total: z.number().int().positive(),
    })
    .transform(({ item, name, action, done, total }) => ({
      type: "export_progress" as const,
      item,
      name,
      action,
      done,
      total,
    })),
  export_finished: z
    .object({
      project_url: z.string().nullish(),
      created: z.number().int().nonnegative(),
      updated: z.number().int().nonnegative(),
      links: z.number().int().nonnegative(),
    })
    .transform(({ project_url, created, updated, links }) => ({
      type: "export_finished" as const,
      projectUrl: project_url ?? null,
      created,
      updated,
      links,
    })),
  gate: z
    .object({
      specialist: z.string(),
      gate: z.string(),
      decision: gateDecisionSchema,
      reason: z.string(),
    })
    .transform(({ specialist, gate, decision, reason }) => ({
      type: "gate" as const,
      specialist,
      gate,
      decision,
      reason,
    })),
} satisfies Record<RunEventType, z.ZodType>;

export type RunEvent = {
  [K in RunEventType]: z.output<(typeof payloadSchemas)[K]>;
}[RunEventType];

const envelopeSchema = z.object({
  run_id: z.string(),
  type: z.string(),
  data: z.unknown(),
  // Optional: the frame that closes a finished run whose stream is gone may carry no timestamp, and a
  // dropped frame would leave the source reconnecting forever.
  ts: z.string().optional(),
});

/** The note shown when the run waits on a question this page cannot read. */
export const UNREADABLE_PAUSE_CODE = "interrupt.unreadable";
export const UNREADABLE_PAUSE_TEXT = "Metis asked something this page could not read. Stop the run and try again.";

export function unreadablePauseNotice(): RunEvent {
  return { type: "notice", code: UNREADABLE_PAUSE_CODE, text: UNREADABLE_PAUSE_TEXT };
}

function isRunEventType(name: string): name is RunEventType {
  return (RUN_EVENT_TYPES as readonly string[]).includes(name);
}

function parseJson(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

/**
 * Parses one SSE frame (`event: <name>`, `data: <raw>`) into a `RunEvent`. Unknown names,
 * malformed JSON and payloads that fail validation give `null`: the caller ignores them.
 */
export function parseRunEvent(name: string, raw: string): RunEvent | null {
  if (!isRunEventType(name)) return null;
  const envelope = envelopeSchema.safeParse(parseJson(raw));
  if (!envelope.success || envelope.data.type !== name) return null;
  const payload = payloadSchemas[name].safeParse(envelope.data.data);
  if (payload.success) return payload.data as RunEvent;
  // A pause the page cannot read must not look like a run that is simply quiet.
  return name === "interrupt" ? unreadablePauseNotice() : null;
}
