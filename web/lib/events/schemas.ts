import { z } from "zod";

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

/**
 * A question, approval or advice decision the run waits on, reduced to what the page shows. For an
 * advice decision `text` is the score run's id, so two decisions are never taken for the same one.
 */
export type PromptInterrupt = { kind: "question" | "approval"; text: string; details?: string };
export type AdviceInterrupt = {
  kind: "advice_decision";
  text: string;
  scoreRunId: string;
  total: number;
  band: z.infer<typeof scoreBandSchema>;
};
export type RunInterrupt = PromptInterrupt | AdviceInterrupt;

export const interruptSchema = z
  .union([
    z.object({ type: z.literal("question"), question: z.string() }),
    z.object({ type: z.literal("approval"), action: z.string(), details: z.unknown().optional() }),
    z.object({
      type: z.literal("advice_decision"),
      score_run_id: z.string(),
      total: z.number(),
      band: scoreBandSchema,
    }),
  ])
  .transform((value): RunInterrupt => {
    if (value.type === "question") return { kind: "question", text: value.question };
    if (value.type === "advice_decision") {
      return { kind: "advice_decision", text: value.score_run_id, scoreRunId: value.score_run_id, total: value.total, band: value.band };
    }
    const details = typeof value.details === "string" && value.details.trim() !== "" ? value.details : undefined;
    return { kind: "approval", text: value.action, ...(details && { details }) };
  });

const nodeSchema = z.object({ node: z.string() });

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
} satisfies Record<RunEventType, z.ZodType>;

export type RunEvent = {
  [K in RunEventType]: z.output<(typeof payloadSchemas)[K]>;
}[RunEventType];

const envelopeSchema = z.object({
  run_id: z.string(),
  type: z.string(),
  data: z.unknown(),
  ts: z.string(),
});

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
  return payload.success ? (payload.data as RunEvent) : null;
}
