const NOTES_OPEN = ">>> Agent notes";
const NOTES_CLOSE = ">>>";

export interface SplitBrief {
  /** The human-readable part of the brief. */
  body: string;
  /** The text inside the Agent notes block, or null when there is none. */
  notes: string | null;
}

/**
 * Splits Linear's collapsible `>>> Agent notes … >>>` block (written by the server's issue brief)
 * off a brief. Markdown would read `>>>` as nested quotes, so the block is shown on its own.
 */
export function splitAgentNotes(description: string): SplitBrief {
  const lines = description.split("\n");
  const start = lines.findIndex((line) => line.trim() === NOTES_OPEN);
  if (start === -1) return { body: description.trim(), notes: null };
  const end = lines.findIndex((line, index) => index > start && line.trim() === NOTES_CLOSE);
  const noteLines = lines.slice(start + 1, end === -1 ? undefined : end);
  const rest = [...lines.slice(0, start), ...(end === -1 ? [] : lines.slice(end + 1))];
  const notes = noteLines.join("\n").trim();
  return { body: rest.join("\n").trim(), notes: notes === "" ? null : notes };
}
