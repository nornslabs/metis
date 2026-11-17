import {
  interruptSchema,
  runErrorSchema,
  runStatusSchema,
  type RunError,
  type RunEvent,
  type RunInterrupt,
  type RunStatus,
} from "./schemas";

/** One specialist step: a row in the step list, with the tool names it called. */
export type RunStep = { readonly node: string; readonly done: boolean; readonly tools: readonly string[] };

/** What the agent message shows for one run, rebuilt from the run view plus the event stream. */
export type RunState = {
  readonly status: RunStatus;
  readonly steps: readonly RunStep[];
  readonly text: string;
  readonly error: RunError | null;
  readonly interrupt: RunInterrupt | null;
};

/** The parts of `RunView` the reducer starts from. */
export type RunSeed = {
  status: string;
  error: Readonly<Record<string, unknown>> | null;
  pending_interrupt: Readonly<Record<string, unknown>> | null;
};

const ACTIVE_STATUSES: readonly RunStatus[] = ["queued", "running", "awaiting_user"];
const FALLBACK_ERROR: RunError = { code: "run.failed", message: "The run failed." };

/** True while a run can still change: the composer shows Stop. */
export function isActiveStatus(status: string): boolean {
  return (ACTIVE_STATUSES as readonly string[]).includes(status);
}

/** True for `succeeded`, `failed` and `cancelled`: the stream ends after one of these. */
export function isTerminalStatus(status: string): boolean {
  return runStatusSchema.safeParse(status).success && !isActiveStatus(status);
}

/** The state before any event: the run view's status, error and pending question. */
export function initialRunState(seed: RunSeed): RunState {
  const status = runStatusSchema.catch("queued").parse(seed.status);
  const error = seed.error ? runErrorSchema.catch(FALLBACK_ERROR).parse(seed.error) : null;
  const interrupt = seed.pending_interrupt
    ? (interruptSchema.safeParse(seed.pending_interrupt).data ?? null)
    : null;
  return { status, steps: [], text: "", error, interrupt };
}

function lastIndexOfNode(steps: readonly RunStep[], node: string): number {
  return steps.findLastIndex((step) => step.node === node);
}

function replaceStep(steps: readonly RunStep[], index: number, step: RunStep): RunStep[] {
  return steps.map((current, i) => (i === index ? step : current));
}

function startStep(steps: readonly RunStep[], node: string): readonly RunStep[] {
  const last = steps[lastIndexOfNode(steps, node)];
  if (last && !last.done) return steps;
  return [...steps, { node, done: false, tools: [] }];
}

function finishStep(steps: readonly RunStep[], node: string): readonly RunStep[] {
  const index = lastIndexOfNode(steps, node);
  const last = steps[index];
  if (!last || last.done) return [...steps, { node, done: true, tools: [] }];
  return replaceStep(steps, index, { ...last, done: true });
}

function addTool(steps: readonly RunStep[], node: string, name: string): readonly RunStep[] {
  const index = lastIndexOfNode(steps, node);
  const last = steps[index];
  if (!last) return [...steps, { node, done: false, tools: [name] }];
  if (last.tools.includes(name)) return steps;
  return replaceStep(steps, index, { ...last, tools: [...last.tools, name] });
}

/** Applies one event and returns a new state; the previous state is never changed. */
export function runReducer(state: RunState, event: RunEvent): RunState {
  switch (event.type) {
    case "run_status":
      return {
        ...state,
        status: event.status,
        error: event.status === "failed" ? (event.error ?? FALLBACK_ERROR) : null,
        interrupt: event.status === "awaiting_user" ? state.interrupt : null,
      };
    case "node_started":
      return { ...state, steps: startStep(state.steps, event.node) };
    case "node_finished":
      return { ...state, steps: finishStep(state.steps, event.node) };
    case "tool_call":
      return { ...state, steps: addTool(state.steps, event.node, event.name) };
    case "token":
      return { ...state, text: state.text + event.text };
    case "interrupt":
      return { ...state, interrupt: event.interrupt };
  }
}
