import { ApiError, describeError } from "@/lib/api/errors";
import { RUN_ENQUEUE_FAILED, SPEC_CONFLICT, SPEC_NOT_EDITABLE, type SpecConfirmed, type SpecOverview, type SpecVersion } from "@/lib/schemas/spec";
import { applySectionEdit } from "@/lib/spec/sections";

/** How long after the last keystroke a change is saved. */
export const AUTOSAVE_DELAY_MS = 700;

/** What the editor does to the outside world; the page binds these to the API and the query cache. */
export interface SpecEditorPorts {
  /** Saves `contentMd` as a new version on top of `baseNumber`. */
  save: (baseNumber: number, contentMd: string) => Promise<SpecVersion>;
  /** Confirms version `number` and resumes the run that waits on it. */
  confirm: (number: number) => Promise<SpecConfirmed>;
  /** Reads the server's latest and confirmed versions. */
  refresh: () => Promise<SpecOverview>;
  /** Tells the page the server's state changed (the query cache takes it). */
  publish: (overview: SpecOverview) => void;
}

export type SaveStatus = "idle" | "dirty" | "saving" | "failed" | "conflict";
export type ConfirmProblem = "enqueue" | "failed" | null;

export interface SpecEditorState {
  readonly latest: SpecVersion | null;
  readonly confirmed: SpecVersion | null;
  /** The text typed but not saved yet, or null. */
  readonly draftMd: string | null;
  readonly status: SaveStatus;
  readonly error: string | null;
  readonly confirming: boolean;
  /** `enqueue`: the spec is confirmed but the run could not continue; Confirm again continues it. */
  readonly confirmProblem: ConfirmProblem;
  /** Grows when the text is replaced from outside (reload, newer server version): fields restart from it. */
  readonly epoch: number;
}

const INITIAL: SpecEditorState = {
  latest: null,
  confirmed: null,
  draftMd: null,
  status: "idle",
  error: null,
  confirming: false,
  confirmProblem: null,
  epoch: 0,
};

/** True once the newest version is the confirmed one: nothing can be edited. */
export function isLocked(state: Pick<SpecEditorState, "latest" | "confirmed">): boolean {
  return state.latest !== null && state.confirmed !== null && state.confirmed.id === state.latest.id;
}

/** The markdown the pane shows: what is typed, else the newest saved version. */
export function currentMarkdown(state: Pick<SpecEditorState, "latest" | "draftMd">): string {
  return state.draftMd ?? state.latest?.content_md ?? "";
}

/**
 * The state behind the Spec pane, its footer and the chat prompt, one per idea. Edits are held
 * and saved as a new version a moment after the last keystroke, one save at a time; edits made
 * during a save are saved right after it on the version it returned. The text typed is never
 * dropped: a failed save keeps it and can be retried.
 */
export class SpecEditor {
  private state: SpecEditorState = INITIAL;
  private readonly listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private inFlight: Promise<void> | null = null;

  constructor(private readonly ports: SpecEditorPorts) {}

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  readonly getState = (): SpecEditorState => this.state;

  /** Takes the server's versions in. Typed text is kept; a newer version replaces nothing mid-edit. */
  sync(overview: SpecOverview): void {
    const { latest, confirmed } = this.state;
    const typing = this.state.draftMd !== null || this.state.status === "saving";
    const newer = overview.latest !== null && (latest === null || overview.latest.number > latest.number);
    if (typing || !newer) {
      if (confirmed?.id !== overview.confirmed?.id) this.set({ confirmed: overview.confirmed });
      if (latest === null && overview.latest !== null) this.set({ latest: overview.latest, confirmed: overview.confirmed });
      return;
    }
    this.set({ latest: overview.latest, confirmed: overview.confirmed, epoch: this.state.epoch + 1 });
  }

  /** One section's new text. Ignored while the spec is locked or in conflict. */
  edit(key: string, value: string): void {
    const { latest, status } = this.state;
    if (latest === null || isLocked(this.state) || status === "conflict") return;
    const base = currentMarkdown(this.state);
    const next = applySectionEdit(base, key, value);
    if (next === base) return;
    this.set({ draftMd: next, status: this.state.status === "saving" ? "saving" : "dirty", error: null });
    this.schedule();
  }

  /** Saves what is pending now. True when nothing is left unsaved. */
  async flush(): Promise<boolean> {
    this.clearTimer();
    for (;;) {
      if (this.inFlight !== null) {
        await this.inFlight;
        continue;
      }
      const { latest, draftMd, status } = this.state;
      if (status === "conflict") return false;
      if (draftMd === null || latest === null || draftMd === latest.content_md) {
        if (draftMd !== null || status === "dirty") this.set({ draftMd: null, status: "idle" });
        return this.state.status !== "failed";
      }
      this.inFlight = this.saveOnce().finally(() => {
        this.inFlight = null;
      });
      await this.inFlight;
      if (this.state.status === "failed" || this.state.status === "conflict") return false;
    }
  }

  /** Replaces the text with the server's newest version; what was typed and unsaved is dropped. */
  async reload(): Promise<void> {
    this.clearTimer();
    try {
      const overview = await this.ports.refresh();
      this.set({
        latest: overview.latest,
        confirmed: overview.confirmed,
        draftMd: null,
        status: "idle",
        error: null,
        epoch: this.state.epoch + 1,
      });
    } catch (caught) {
      this.set({ error: describeError(caught) });
    }
  }

  /** Confirms the newest version, after saving what is pending. Confirming again continues a run that could not. */
  async confirm(): Promise<void> {
    if (this.state.confirming) return;
    this.set({ confirming: true, confirmProblem: null });
    try {
      if (!(await this.flush())) return;
      const latest = this.state.latest;
      if (latest === null) return;
      const result = await this.ports.confirm(latest.number);
      this.set({ latest: result.confirmed, confirmed: result.confirmed, confirmProblem: null });
      this.ports.publish({ latest: result.confirmed, confirmed: result.confirmed });
    } catch (caught) {
      await this.failConfirm(caught);
    } finally {
      this.set({ confirming: false });
    }
  }

  private async saveOnce(): Promise<void> {
    const { latest, draftMd } = this.state;
    if (latest === null || draftMd === null) return;
    this.set({ status: "saving", error: null });
    try {
      const saved = await this.ports.save(latest.number, draftMd);
      const stillTyping = this.state.draftMd !== draftMd;
      this.set({ latest: saved, draftMd: stillTyping ? this.state.draftMd : null, status: stillTyping ? "dirty" : "idle" });
      this.ports.publish({ latest: saved, confirmed: this.state.confirmed });
    } catch (caught) {
      await this.failSave(caught);
    }
  }

  private async failSave(caught: unknown): Promise<void> {
    if (caught instanceof ApiError && caught.code === SPEC_CONFLICT) {
      this.set({ status: "conflict", error: null });
      return;
    }
    if (caught instanceof ApiError && caught.code === SPEC_NOT_EDITABLE) {
      // The spec was confirmed elsewhere: show the server's version, locked.
      await this.reload();
      return;
    }
    this.set({ status: "failed", error: describeError(caught) });
  }

  private async failConfirm(caught: unknown): Promise<void> {
    if (caught instanceof ApiError && caught.code === SPEC_CONFLICT) {
      this.set({ status: "conflict", error: null });
      return;
    }
    if (caught instanceof ApiError && caught.code === SPEC_NOT_EDITABLE) {
      // Confirmed elsewhere already: show the server's version, locked.
      await this.reload();
      return;
    }
    if (caught instanceof ApiError && caught.code === RUN_ENQUEUE_FAILED) {
      // The server kept the confirmation: show it locked, and let Confirm continue the run.
      await this.reload();
      this.set({ confirmProblem: "enqueue", error: describeError(caught) });
      return;
    }
    this.set({ confirmProblem: "failed", error: describeError(caught) });
  }

  private schedule(): void {
    this.clearTimer();
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.flush();
    }, AUTOSAVE_DELAY_MS);
  }

  private clearTimer(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  private set(patch: Partial<SpecEditorState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener();
  }
}
