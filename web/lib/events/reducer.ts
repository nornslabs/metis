import {
  UNREADABLE_PAUSE_CODE,
  UNREADABLE_PAUSE_TEXT,
  interruptSchema,
  runErrorSchema,
  runStatusSchema,
  type RunError,
  type RunEvent,
  type RunInterrupt,
  type RunStatus,
} from "./schemas";

/** One specialist step: a row in the step list, with the tool names it called. */
export type RunStep = {
  readonly node: string;
  readonly done: boolean;
  /** Set by a `notice` that says the step did no work (research without an Exa key). */
  readonly skipped?: boolean;
  readonly tools: readonly string[];
};

/** A server note about the run (`notice` event), shown under the steps. */
export type RunNotice = { readonly code: string; readonly text: string };

/** Notice codes that mean a node was skipped, so its step is marked. */
const SKIPPED_NODE_BY_CODE: Readonly<Record<string, string>> = { "research.skipped_no_exa": "researcher" };

/** What the agent message shows for one run, rebuilt from the run view plus the event stream. */
export type RunState = {
  readonly status: RunStatus;
  readonly steps: readonly RunStep[];
  /** Notices in the order they arrived, one per code (a replay does not repeat them). */
  readonly notices: readonly RunNotice[];
  readonly text: string;
  readonly error: RunError | null;
  readonly interrupt: RunInterrupt | null;
  /**
   * How many `interrupt` events this page has seen. A repeated question or a second approval is a
   * new interrupt with a new count, so local answers can be tied to one interrupt, not to its text.
   */
  readonly interruptCount: number;
  /** The newest score run the stream announced (`score` event); a change refetches the scores. */
  readonly scoreRunId: string | null;
};

/** The parts of `RunView` the reducer starts from. */
export type RunSeed = {
  status: string;
  error: Readonly<Record<string, unknown>> | null;
  pending_interrupt: Readonly<Record<string, unknown>> | null;
};

/** An event from the stream, or a `sync` from the run view when the stream is silent. */
export type RunAction = RunEvent | { readonly type: "sync"; readonly seed: RunSeed };

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
  const parsed = seed.pending_interrupt ? interruptSchema.safeParse(seed.pending_interrupt) : null;
  const interrupt = parsed?.success ? parsed.data : null;
  const notices: readonly RunNotice[] =
    parsed && !parsed.success ? [{ code: UNREADABLE_PAUSE_CODE, text: UNREADABLE_PAUSE_TEXT }] : [];
  return { status, steps: [], notices, text: "", error, interrupt, interruptCount: 0, scoreRunId: null };
}

function lastIndexOfNode(steps: readonly RunStep[], node: string): number {
  return steps.findLastIndex((step) => step.node === node);
}

function replaceStep(steps: readonly RunStep[], index: number, step: RunStep): RunStep[] {
  return steps.map((current, i) => (i === index ? step : current));
}

function startStep(steps: readonly RunStep[], node: string): readonly RunStep[] {
  const last = steps[lastIndexOfNode(steps, node)];
  // A running row, or one a notice already marked skipped, is not started again.
  if (last && (!last.done || last.skipped)) return steps;
  return [...steps, { node, done: false, tools: [] }];
}

function finishStep(steps: readonly RunStep[], node: string): readonly RunStep[] {
  const index = lastIndexOfNode(steps, node);
  const last = steps[index];
  if (last?.skipped) return steps;
  if (!last || last.done) return [...steps, { node, done: true, tools: [] }];
  return replaceStep(steps, index, { ...last, done: true });
}

function skipStep(steps: readonly RunStep[], node: string): readonly RunStep[] {
  const index = lastIndexOfNode(steps, node);
  const last = steps[index];
  if (!last) return [...steps, { node, done: true, skipped: true, tools: [] }];
  return replaceStep(steps, index, { ...last, done: true, skipped: true });
}

function closeRunningSteps(steps: readonly RunStep[]): readonly RunStep[] {
  return steps.map((step) => (step.done ? step : { ...step, done: true }));
}

function addNotice(state: RunState, notice: RunNotice): RunState {
  if (state.notices.some((known) => known.code === notice.code)) return state;
  const node = SKIPPED_NODE_BY_CODE[notice.code];
  return {
    ...state,
    notices: [...state.notices, notice],
    steps: node ? skipStep(state.steps, node) : state.steps,
  };
}

function addTool(steps: readonly RunStep[], node: string, name: string): readonly RunStep[] {
  const index = lastIndexOfNode(steps, node);
  const last = steps[index];
  if (!last) return [...steps, { node, done: false, tools: [name] }];
  if (last.tools.includes(name)) return steps;
  return replaceStep(steps, index, { ...last, tools: [...last.tools, name] });
}

function sameInterrupt(a: RunInterrupt | null, b: RunInterrupt | null): boolean {
  return a === b || (a !== null && b !== null && a.kind === b.kind && a.text === b.text);
}

/**
 * Catches up with the run view: a status or pause the stream has not delivered. A finished run
 * stays finished, and a view that shows nothing new returns the same state. Steps and text come
 * only from the stream. A view read just before the user answered could show the old pause for
 * one poll; the stream's next `run_status` corrects it.
 */
function syncWithView(state: RunState, seed: RunSeed): RunState {
  if (isTerminalStatus(state.status)) return state;
  const view = initialRunState(seed);
  if (view.status === state.status && sameInterrupt(view.interrupt, state.interrupt)) return state;
  const newPause = view.interrupt !== null && !sameInterrupt(view.interrupt, state.interrupt);
  return {
    ...state,
    status: view.status,
    error: view.error,
    interrupt: view.interrupt,
    interruptCount: newPause ? state.interruptCount + 1 : state.interruptCount,
  };
}

/** Applies one event and returns a new state; the previous state is never changed. */
export function runReducer(state: RunState, event: RunAction): RunState {
  switch (event.type) {
    case "sync":
      return syncWithView(state, event.seed);
    case "run_status":
      return {
        ...state,
        status: event.status,
        error: event.status === "failed" ? (event.error ?? FALLBACK_ERROR) : null,
        interrupt: event.status === "awaiting_user" ? state.interrupt : null,
        // A finished run has no step left running (the skip path ends without a spinner).
        steps: event.status === "succeeded" ? closeRunningSteps(state.steps) : state.steps,
      };
    case "node_started":
      return { ...state, steps: startStep(state.steps, event.node) };
    case "node_finished":
      return { ...state, steps: finishStep(state.steps, event.node) };
    case "tool_call":
      return { ...state, steps: addTool(state.steps, event.node, event.name) };
    case "token":
      return { ...state, text: state.text + event.text };
    case "notice":
      return addNotice(state, { code: event.code, text: event.text });
    case "score":
      return { ...state, scoreRunId: event.scoreRunId };
    case "interrupt":
      return { ...state, interrupt: event.interrupt, interruptCount: state.interruptCount + 1 };
  }
}
