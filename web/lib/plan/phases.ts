import { PHASE_LIMITS, type ReviewedPhase } from "@/lib/schemas/plan";

/** A phase in the review. `key` is stable while the phase is edited or moved, so a field keeps its focus. */
export interface DraftPhase extends ReviewedPhase {
  readonly key: string;
}

export type PhaseField = keyof ReviewedPhase;

let nextKey = 0;
function newKey(): string {
  nextKey += 1;
  return `phase-${nextKey}`;
}

/** The proposed phases, each given a key. */
export function toDraft(phases: readonly ReviewedPhase[]): readonly DraftPhase[] {
  return phases.map((phase) => ({ ...phase, key: newKey() }));
}

/** What the resume answer carries: the phases without keys, text trimmed. */
export function toReviewed(phases: readonly DraftPhase[]): readonly ReviewedPhase[] {
  return phases.map(({ name, goal, exit_criteria }) => ({
    name: name.trim(),
    goal: goal.trim(),
    exit_criteria: exit_criteria.trim(),
  }));
}

export function renamePhase(phases: readonly DraftPhase[], key: string, field: PhaseField, value: string): readonly DraftPhase[] {
  return phases.map((phase) => (phase.key === key ? { ...phase, [field]: value } : phase));
}

/** Moves a phase one place up (`-1`) or down (`1`); at an end it stays. */
export function movePhase(phases: readonly DraftPhase[], key: string, step: -1 | 1): readonly DraftPhase[] {
  const from = phases.findIndex((phase) => phase.key === key);
  const to = from + step;
  if (from < 0 || to < 0 || to >= phases.length) return phases;
  const next = [...phases];
  const moved = next[from];
  const swapped = next[to];
  if (!moved || !swapped) return phases;
  next[from] = swapped;
  next[to] = moved;
  return next;
}

/** Adds an empty phase at the end, unless the plan already has the most phases. */
export function addPhase(phases: readonly DraftPhase[]): readonly DraftPhase[] {
  if (phases.length >= PHASE_LIMITS.maxPhases) return phases;
  return [...phases, { key: newKey(), name: "", goal: "", exit_criteria: "" }];
}

/** Removes a phase; the last one stays (a plan always has a phase). */
export function removePhase(phases: readonly DraftPhase[], key: string): readonly DraftPhase[] {
  if (phases.length <= 1) return phases;
  return phases.filter((phase) => phase.key !== key);
}

/** The first reason the list cannot be sent (named like the review shows it), or null. */
export function phasesProblem(phases: readonly DraftPhase[]): string | null {
  if (phases.length === 0) return "Add at least one phase.";
  if (phases.length > PHASE_LIMITS.maxPhases) return `Use at most ${PHASE_LIMITS.maxPhases} phases.`;
  for (const [index, phase] of phases.entries()) {
    const label = `P${index + 1}`;
    const name = phase.name.trim();
    const goal = phase.goal.trim();
    const exit = phase.exit_criteria.trim();
    if (name === "") return `${label} needs a name.`;
    if (name.length > PHASE_LIMITS.name) return `${label}'s name is over ${PHASE_LIMITS.name} characters.`;
    if (goal === "") return `${label} needs a goal.`;
    if (exit === "") return `${label} needs a "Done when".`;
    if (goal.length > PHASE_LIMITS.text || exit.length > PHASE_LIMITS.text) {
      return `${label} has text over ${PHASE_LIMITS.text} characters.`;
    }
  }
  return null;
}

/** True when the phases differ from the proposal (text compared trimmed). */
export function isEdited(phases: readonly DraftPhase[], proposed: readonly ReviewedPhase[]): boolean {
  const current = toReviewed(phases);
  if (current.length !== proposed.length) return true;
  return current.some((phase, index) => {
    const original = proposed[index];
    return (
      !original ||
      phase.name !== original.name.trim() ||
      phase.goal !== original.goal.trim() ||
      phase.exit_criteria !== original.exit_criteria.trim()
    );
  });
}
