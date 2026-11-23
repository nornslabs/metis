import type { SourceEntry } from "@/lib/research/sources";
import { titleSlug } from "@/lib/text/slug";

function line(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/** `metis-<idea>-sources.md`, the idea's title as a short slug. */
export function sourcesFileName(ideaTitle: string): string {
  return `metis-${titleSlug(ideaTitle)}-sources.md`;
}

/** The Sources list as Markdown, numbered like the pane. Entries are http(s) pages only (see `buildSourceIndex`). */
export function buildSourcesReport(ideaTitle: string, entries: readonly SourceEntry[]): string {
  const title = line(ideaTitle) || "Untitled idea";
  const rows = entries.map((entry) => `${entry.number}. [${line(entry.title).replace(/[[\]]/g, "")}](<${entry.href}>) — ${entry.domain}`);
  return [`# Sources: ${title}`, "", ...(rows.length > 0 ? rows : ["No sources."]), ""].join("\n");
}
