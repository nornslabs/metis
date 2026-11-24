import { describeError, isApiError } from "@/lib/api/errors";
import { PLAN_CONFLICT, PLAN_NOT_EDITABLE, type Plan, type TaskPatch } from "@/lib/schemas/plan";

export type PlanSaveStatus = "idle" | "saving" | "failed" | "conflict";

export interface PlanEditorState {
  readonly status: PlanSaveStatus;
  readonly error: string | null;
  /** How many saves have succeeded since the pane opened; the footer says "Saved" after the first. */
  readonly saved: number;
}

/** What the editor does to the outside world; the page binds these to the API and the query cache. */
export interface PlanEditorPorts {
  /** The plan as the page has it (its `version` is the base of the next save). */
  current: () => Plan | null;
  save: (planId: string, taskId: string, version: number, patch: TaskPatch) => Promise<Plan>;
  refresh: () => Promise<Plan | null>;
  /** Tells the page the server's plan changed (the query cache takes it). */
  publish: (plan: Plan | null) => void;
}

const INITIAL: PlanEditorState = { status: "idle", error: null, saved: 0 };

/**
 * The task edits of one idea's plan. A change is saved as soon as it is made, one save at a time;
 * changes made while one is saving wait and go out on the version the previous save returned. A
 * failed save keeps its change for Retry; a stale version pauses saving until Reload.
 */
export class PlanEditor {
  private state: PlanEditorState = INITIAL;
  private readonly listeners = new Set<() => void>();
  private pending = new Map<string, TaskPatch>();
  private running = false;

  constructor(private readonly ports: PlanEditorPorts) {}

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  readonly getState = (): PlanEditorState => this.state;

  /** Queues a change to one task (changes to the same task merge) and starts saving. */
  edit(taskId: string, patch: TaskPatch): void {
    if (this.state.status === "conflict") return;
    this.pending = new Map(this.pending).set(taskId, { ...this.pending.get(taskId), ...patch });
    void this.flush();
  }

  /** Saves what waits. Also the Retry after a failed save. */
  async flush(): Promise<void> {
    if (this.running || this.state.status === "conflict") return;
    this.running = true;
    this.set({ ...this.state, status: "saving", error: null });
    try {
      while (this.pending.size > 0) {
        const next = this.pending.entries().next();
        if (next.done) break;
        const [taskId, patch] = next.value;
        const plan = this.ports.current();
        if (plan === null) break;
        const saved = await this.ports.save(plan.id, taskId, plan.version, patch);
        // A change made to this task while it saved is a newer patch: it stays queued.
        if (this.pending.get(taskId) === patch) this.pending = new Map([...this.pending].filter(([id]) => id !== taskId));
        this.ports.publish(saved);
        this.set({ ...this.state, saved: this.state.saved + 1 });
      }
      this.set({ ...this.state, status: "idle", error: null });
    } catch (error: unknown) {
      await this.fail(error);
    } finally {
      this.running = false;
    }
  }

  /** Drops the changes not saved and takes the server's plan. */
  async reload(): Promise<void> {
    await this.takeServerPlan();
  }

  private async fail(error: unknown): Promise<void> {
    if (isApiError(error) && error.code === PLAN_CONFLICT) {
      this.set({ ...this.state, status: "conflict", error: null });
      return;
    }
    if (isApiError(error) && error.code === PLAN_NOT_EDITABLE) {
      await this.takeServerPlan();
      return;
    }
    this.set({ ...this.state, status: "failed", error: describeError(error) });
  }

  /** The plan was fixed (ready) in the meantime: drop what waits and show it as the server has it. */
  private async takeServerPlan(): Promise<void> {
    this.pending = new Map();
    try {
      this.ports.publish(await this.ports.refresh());
      this.set({ ...this.state, status: "idle", error: null });
    } catch (error: unknown) {
      this.set({ ...this.state, status: "failed", error: describeError(error) });
    }
  }

  private set(next: PlanEditorState): void {
    this.state = next;
    for (const listener of this.listeners) listener();
  }
}
