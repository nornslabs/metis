import { describeError } from "@/lib/api/errors";
import {
  addPhase,
  isEdited,
  movePhase,
  phasesProblem,
  removePhase,
  renamePhase,
  toDraft,
  toReviewed,
  type DraftPhase,
  type PhaseField,
} from "@/lib/plan/phases";
import { reviewedPhaseSchema, type ReviewedPhase } from "@/lib/schemas/plan";
import { z } from "zod";

export type ReviewStatus = "idle" | "sending" | "sent" | "failed";

export interface PhaseReviewState {
  /** The run that waits on the review, or null before the first interrupt. */
  readonly runId: string | null;
  /** The phases the Planner proposed (what "edited" is measured against). */
  readonly proposed: readonly ReviewedPhase[];
  readonly phases: readonly DraftPhase[];
  readonly status: ReviewStatus;
  readonly error: string | null;
}

/** What the review does to the outside world; the page binds it to the API. */
export interface PhaseReviewPorts {
  /** Answers the `phase_review` interrupt of `runId` with the reviewed phases. */
  resume: (runId: string, phases: readonly ReviewedPhase[]) => Promise<void>;
}

const INITIAL: PhaseReviewState = { runId: null, proposed: [], phases: [], status: "idle", error: null };
/** The edits plus the proposal they were made on, so a new proposal never inherits an old draft. */
const storedSchema = z.object({ proposed: z.array(reviewedPhaseSchema), phases: z.array(reviewedPhaseSchema).min(1) });

function storageKey(runId: string): string {
  return `metis:phase-review:${runId}`;
}

/** Per-viewer convenience: the edits survive a reload. Never throws (private windows, blocked storage). */
function readStored(runId: string, proposed: readonly ReviewedPhase[]): readonly ReviewedPhase[] | null {
  try {
    const raw = window.sessionStorage.getItem(storageKey(runId));
    if (raw === null) return null;
    const parsed = storedSchema.safeParse(JSON.parse(raw));
    return parsed.success && sameProposal(parsed.data.proposed, proposed) ? parsed.data.phases : null;
  } catch {
    return null;
  }
}

function writeStored(runId: string, edit: { proposed: readonly ReviewedPhase[]; phases: readonly ReviewedPhase[] } | null): void {
  try {
    if (edit === null) window.sessionStorage.removeItem(storageKey(runId));
    else window.sessionStorage.setItem(storageKey(runId), JSON.stringify(edit));
  } catch {
    // Storage is a convenience: the edits still live in memory.
  }
}

function sameProposal(a: readonly ReviewedPhase[], b: readonly ReviewedPhase[]): boolean {
  return (
    a.length === b.length &&
    a.every((phase, index) => {
      const other = b[index];
      return other !== undefined && phase.name === other.name && phase.goal === other.goal && phase.exit_criteria === other.exit_criteria;
    })
  );
}

/**
 * The phase review of one idea, shared by the pane, its footer and the chat prompt. Edits are held
 * here (and in session storage) and sent only by `approve`, which answers the run's interrupt.
 */
export class PhaseReview {
  private state: PhaseReviewState = INITIAL;
  private readonly listeners = new Set<() => void>();

  constructor(private readonly ports: PhaseReviewPorts) {}

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  readonly getState = (): PhaseReviewState => this.state;

  /** Takes the pending interrupt in. A new run or a different proposal starts over (stored edits are restored). */
  sync(runId: string, proposed: readonly ReviewedPhase[]): void {
    if (this.state.runId === runId && sameProposal(this.state.proposed, proposed)) return;
    const stored = readStored(runId, proposed);
    this.set({ runId, proposed, phases: toDraft(stored ?? proposed), status: "idle", error: null });
  }

  edit(key: string, field: PhaseField, value: string): void {
    this.change(renamePhase(this.state.phases, key, field, value));
  }

  move(key: string, step: -1 | 1): void {
    this.change(movePhase(this.state.phases, key, step));
  }

  add(): void {
    this.change(addPhase(this.state.phases));
  }

  remove(key: string): void {
    this.change(removePhase(this.state.phases, key));
  }

  /** Why Approve is not possible now, or null. */
  blockedReason(): string | null {
    if (this.state.status === "sending") return "Sending…";
    if (this.state.status === "sent") return "Already approved";
    return phasesProblem(this.state.phases);
  }

  /** Sends the phases (the proposal itself when nothing changed). A failure keeps every edit. */
  async approve(): Promise<void> {
    const { runId, phases } = this.state;
    if (runId === null || this.blockedReason() !== null) return;
    this.set({ ...this.state, status: "sending", error: null });
    try {
      // Untouched means the proposal itself, byte for byte (the reviewed copy is trimmed).
      await this.ports.resume(runId, this.edited() ? toReviewed(phases) : this.state.proposed);
      writeStored(runId, null);
      this.set({ ...this.state, status: "sent", error: null });
    } catch (error: unknown) {
      this.set({ ...this.state, status: "failed", error: describeError(error) });
    }
  }

  /** True once the user changed anything from the proposal. */
  edited(): boolean {
    return isEdited(this.state.phases, this.state.proposed);
  }

  private change(phases: readonly DraftPhase[]): void {
    if (phases === this.state.phases || this.state.runId === null || this.state.status === "sending" || this.state.status === "sent") return;
    writeStored(this.state.runId, { proposed: this.state.proposed, phases: toReviewed(phases) });
    this.set({ ...this.state, phases, status: "idle", error: null });
  }

  private set(next: PhaseReviewState): void {
    this.state = next;
    for (const listener of this.listeners) listener();
  }
}
