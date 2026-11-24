/**
 * What changed between two versions of a spec, section by section. Computed in the browser from the
 * two markdown texts (the server has no diff route). Text sections are compared word by word, list
 * sections item by item. Pure: nothing here mutates its input.
 */
import { SECTION_DEFS, listItems, sectionText, unknownSections } from "@/lib/spec/sections";

export type DiffKind = "same" | "ins" | "del";

/** One run of the diff: words (text sections) or one item (list sections) with the same fate. */
export interface DiffOp {
  readonly kind: DiffKind;
  readonly text: string;
}

export interface SectionChange {
  readonly key: string;
  readonly label: string;
  /** `list` when both versions hold only bullet items; otherwise the section is compared as text. */
  readonly kind: "text" | "list";
  readonly ops: readonly DiffOp[];
  /** Words (text) or items (list) added. */
  readonly inserted: number;
  /** Words (text) or items (list) removed. */
  readonly deleted: number;
}

export interface SpecDiff {
  readonly sections: readonly SectionChange[];
  readonly inserted: number;
  readonly deleted: number;
}

/** True when the section has no difference. */
export function isUnchanged(change: SectionChange): boolean {
  return change.inserted === 0 && change.deleted === 0;
}

type Step<T> = { readonly kind: DiffKind; readonly value: T };

/** Longest-common-subsequence diff of two token lists. */
function lcsSteps<T>(from: readonly T[], to: readonly T[]): readonly Step<T>[] {
  const rows = from.length;
  const cols = to.length;
  const table: number[][] = Array.from({ length: rows + 1 }, () => new Array<number>(cols + 1).fill(0));
  for (let i = rows - 1; i >= 0; i--) {
    for (let j = cols - 1; j >= 0; j--) {
      table[i]![j] = from[i] === to[j] ? table[i + 1]![j + 1]! + 1 : Math.max(table[i + 1]![j]!, table[i]![j + 1]!);
    }
  }
  const steps: Step<T>[] = [];
  let i = 0;
  let j = 0;
  while (i < rows && j < cols) {
    if (from[i] === to[j]) {
      steps.push({ kind: "same", value: from[i]! });
      i++;
      j++;
    } else if (table[i + 1]![j]! >= table[i]![j + 1]!) {
      steps.push({ kind: "del", value: from[i++]! });
    } else {
      steps.push({ kind: "ins", value: to[j++]! });
    }
  }
  while (i < rows) steps.push({ kind: "del", value: from[i++]! });
  while (j < cols) steps.push({ kind: "ins", value: to[j++]! });
  return steps;
}

function words(text: string): readonly string[] {
  return text.split(/\s+/).filter((word) => word !== "");
}

/** Joins neighbouring steps of one kind into a single op, so a changed phrase is one run. */
function wordOps(steps: readonly Step<string>[]): readonly DiffOp[] {
  const ops: DiffOp[] = [];
  for (const step of steps) {
    const last = ops.at(-1);
    if (last !== undefined && last.kind === step.kind) ops[ops.length - 1] = { kind: last.kind, text: `${last.text} ${step.value}` };
    else ops.push({ kind: step.kind, text: step.value });
  }
  return ops;
}

function count(steps: readonly Step<unknown>[], kind: DiffKind): number {
  return steps.filter((step) => step.kind === kind).length;
}

function compare(key: string, label: string, kind: "text" | "list", from: string, to: string): SectionChange {
  const fromItems = kind === "list" ? listItems(from) : null;
  const toItems = kind === "list" ? listItems(to) : null;
  if (fromItems !== null && toItems !== null) {
    const steps = lcsSteps(fromItems, toItems);
    const ops = steps.map((step) => ({ kind: step.kind, text: step.value }));
    return { key, label, kind: "list", ops, inserted: count(steps, "ins"), deleted: count(steps, "del") };
  }
  const steps = lcsSteps(words(from), words(to));
  return { key, label, kind: "text", ops: wordOps(steps), inserted: count(steps, "ins"), deleted: count(steps, "del") };
}

/** The sections of both versions, in the pane's order, with what was added and removed in each. */
export function diffSpecs(fromMd: string, toMd: string): SpecDiff {
  const sections: SectionChange[] = [];
  for (const def of SECTION_DEFS) {
    const from = sectionText(fromMd, def.key);
    const to = sectionText(toMd, def.key);
    if (!def.always && from === "" && to === "") continue;
    sections.push(compare(def.key, def.label, def.kind, from, to));
  }
  const unknownTo = unknownSections(toMd);
  const unknownFrom = unknownSections(fromMd);
  const headings = [...new Set([...unknownFrom, ...unknownTo].map((block) => block.heading))];
  for (const heading of headings) {
    const from = unknownFrom.find((block) => block.heading === heading)?.text ?? "";
    const to = unknownTo.find((block) => block.heading === heading)?.text ?? "";
    if (from === "" && to === "") continue;
    sections.push(compare(`other:${heading}`, heading, "text", from, to));
  }
  return {
    sections,
    inserted: sections.reduce((total, section) => total + section.inserted, 0),
    deleted: sections.reduce((total, section) => total + section.deleted, 0),
  };
}
