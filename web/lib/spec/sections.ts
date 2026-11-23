/**
 * The spec as the pane shows it. A version's text is markdown with `## ` headings (the server's
 * template, `ideas/dto/spec.py`). Reading splits on those headings; an edit replaces only its own
 * block, so every other block keeps its exact text, including headings this code does not know.
 * Pure functions: nothing here mutates its input.
 */

/** What the server writes under a section with nothing in it. */
export const NONE_TEXT = "None.";

export type SectionKind = "text" | "list";

interface SectionDef {
  readonly key: string;
  /** The server's heading, used to find the block and to write one that is missing. */
  readonly heading: string;
  /** The label the pane shows. */
  readonly label: string;
  readonly kind: SectionKind;
  readonly placeholder: string;
  /** Shown even when empty. The others show only with content. */
  readonly always: boolean;
}

export const SECTION_DEFS: readonly SectionDef[] = [
  { key: "problem", heading: "Problem", label: "Problem", kind: "text", placeholder: "What problem does it solve?", always: true },
  { key: "target_users", heading: "Target users", label: "Users", kind: "text", placeholder: "Who is it for?", always: true },
  { key: "key_features", heading: "Key features (MVP and later)", label: "Core features", kind: "list", placeholder: "Add a feature", always: true },
  { key: "success_metrics", heading: "Success metrics", label: "Success metric", kind: "text", placeholder: "How will you know it works?", always: true },
  { key: "non_goals", heading: "Non-goals", label: "Out of scope", kind: "list", placeholder: "Add something left out", always: true },
  { key: "solution", heading: "Solution", label: "Solution", kind: "text", placeholder: "How does it solve it?", always: false },
  { key: "competitive_edge", heading: "Competitive edge", label: "Competitive edge", kind: "text", placeholder: "Why this and not the others?", always: false },
  { key: "risks", heading: "Risks", label: "Risks", kind: "text", placeholder: "What could go wrong?", always: false },
  { key: "open_questions", heading: "Open questions", label: "Open questions", kind: "text", placeholder: "What is still unknown?", always: false },
];

const HEADING_LINE = /^##[ \t]+(.+?)[ \t]*#*[ \t]*$/gm;
const BULLET = /^[ \t]*[-*][ \t]+(.*)$/;
const KEY_BY_HEADING = new Map(SECTION_DEFS.map((def) => [def.heading.toLowerCase(), def.key]));

interface Block {
  /** The block's exact text: its heading line and everything up to the next heading. */
  readonly raw: string;
  /** The template key for a known heading, else null. */
  readonly key: string | null;
  /** The heading line's own text. */
  readonly headingLine: string;
}

interface Parsed {
  readonly preamble: string;
  readonly blocks: readonly Block[];
}

function parse(contentMd: string): Parsed {
  const starts = [...contentMd.matchAll(HEADING_LINE)].map((match) => ({
    index: match.index,
    line: match[0],
    heading: match[1] ?? "",
  }));
  if (starts.length === 0) return { preamble: contentMd, blocks: [] };
  const blocks = starts.map((start, position) => {
    const end = starts[position + 1]?.index ?? contentMd.length;
    return {
      raw: contentMd.slice(start.index, end),
      key: KEY_BY_HEADING.get(start.heading.toLowerCase()) ?? null,
      headingLine: start.line,
    };
  });
  return { preamble: contentMd.slice(0, starts[0]!.index), blocks };
}

function bodyOf(block: Block): string {
  return block.raw.slice(block.headingLine.length).trim();
}

/** The text under a template section, or "" when it is missing or says `None.`. */
export function sectionText(contentMd: string, key: string): string {
  const block = parse(contentMd).blocks.find((candidate) => candidate.key === key);
  const text = block ? bodyOf(block) : "";
  return text === NONE_TEXT ? "" : text;
}

/** The bullet items of a list text, or null when the text is not only bullet lines. */
export function listItems(text: string): readonly string[] | null {
  const lines = text.split("\n").filter((line) => line.trim() !== "");
  const items: string[] = [];
  for (const line of lines) {
    const match = BULLET.exec(line);
    if (match === null) return null;
    items.push((match[1] ?? "").trim());
  }
  return items;
}

/** Items as the bullet text the server stores; empty items are dropped. */
export function joinItems(items: readonly string[]): string {
  return items
    .map((item) => item.trim())
    .filter((item) => item !== "")
    .map((item) => `- ${item}`)
    .join("\n");
}

/** One section as the pane shows it. A list section whose text is not all bullets edits as text. */
export interface SectionView {
  readonly key: string;
  readonly label: string;
  readonly placeholder: string;
  readonly kind: SectionKind;
  /** The section's text (for a list, the bullet text). */
  readonly text: string;
  /** The items of a list section; empty for a text section. */
  readonly items: readonly string[];
}

/** The sections to show for a version: the five named ones always, the others only with content. */
export function visibleSections(contentMd: string): readonly SectionView[] {
  const views: SectionView[] = [];
  for (const def of SECTION_DEFS) {
    const text = sectionText(contentMd, def.key);
    if (!def.always && text === "") continue;
    const items = def.kind === "list" ? listItems(text) : null;
    const asList = def.kind === "list" && items !== null;
    views.push({
      key: def.key,
      label: def.label,
      placeholder: def.placeholder,
      kind: asList ? "list" : "text",
      text,
      items: asList ? items : [],
    });
  }
  return views;
}

/** The markdown with one section's text replaced; every other block stays byte for byte. */
export function applySectionEdit(contentMd: string, key: string, value: string): string {
  const { preamble, blocks } = parse(contentMd);
  const text = value.trim() === "" ? NONE_TEXT : value.trim();
  const index = blocks.findIndex((block) => block.key === key);
  if (index === -1) {
    const def = SECTION_DEFS.find((candidate) => candidate.key === key);
    if (def === undefined) return contentMd;
    const separator = contentMd.trim() === "" ? "" : `${contentMd.replace(/\s*$/, "")}\n\n`;
    return `${separator}## ${def.heading}\n\n${text}\n`;
  }
  const target = blocks[index]!;
  const trailing = /\s*$/.exec(target.raw)?.[0] ?? "";
  const replaced = `${target.headingLine}\n\n${text}${trailing}`;
  return preamble + blocks.map((block, position) => (position === index ? replaced : block.raw)).join("");
}
