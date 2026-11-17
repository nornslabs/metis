import { z } from "zod";

import type { components } from "@/lib/api/schema";

// Limits match the server's `NewIdea` validation (SHIP-218).
export const TEXT_MIN = 10;
export const TEXT_MAX = 10_000;
export const TITLE_MIN = 3;
export const TITLE_MAX = 120;

/** The idea's title: its first non-empty line, trimmed and cut to `TITLE_MAX` characters. */
export function deriveTitle(text: string): string {
  const firstLine = text.split("\n").find((line) => line.trim() !== "") ?? "";
  return firstLine.trim().slice(0, TITLE_MAX).trim();
}

export const ideaFormSchema = z.object({
  text: z
    .string()
    .trim()
    .min(TEXT_MIN, `Describe your idea in at least ${TEXT_MIN} characters.`)
    .max(TEXT_MAX, `Keep your idea under ${TEXT_MAX.toLocaleString("en-US")} characters.`)
    .refine((text) => deriveTitle(text).length >= TITLE_MIN, {
      message: `Start with a first line of at least ${TITLE_MIN} characters; it becomes the title.`,
    }),
});

export type IdeaFormValues = z.input<typeof ideaFormSchema>;

/** The `POST /v1/ideas` body for valid form values. */
export function toNewIdea(values: IdeaFormValues): components["schemas"]["NewIdea"] {
  const rawText = values.text.trim();
  return { title: deriveTitle(rawText), raw_text: rawText };
}
