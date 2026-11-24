import type { components } from "@/lib/api/schema";

export type ResearchView = components["schemas"]["ResearchView"];
export type ResearchItem = ResearchView["items"][number];
export type Competitor = ResearchView["competitors"][number];

/** A competitor overlapping the idea by at least this much is Direct, else Adjacent. */
export const DIRECT_OVERLAP = 0.5;
const HIGH_CONFIDENCE = 0.7;
const MEDIUM_CONFIDENCE = 0.4;

/** The link to open, or `null` unless it is an http(s) URL: agent- and web-sourced links are untrusted. */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

/** The host without `www.`, or `null` when the URL is not a safe link. */
export function domainOf(url: string | null | undefined): string | null {
  const href = safeHref(url);
  return href ? new URL(href).hostname.replace(/^www\./, "") : null;
}

/** `0.62` → `62%`. */
export function overlapPercent(overlap: number): string {
  return `${Math.round(overlap * 100)}%`;
}

export type CompetitorRelation = "Direct" | "Adjacent";

export function competitorRelation(overlap: number): CompetitorRelation {
  return overlap >= DIRECT_OVERLAP ? "Direct" : "Adjacent";
}

export function confidenceLabel(confidence: number): "High" | "Medium" | "Low" {
  if (confidence >= HIGH_CONFIDENCE) return "High";
  if (confidence >= MEDIUM_CONFIDENCE) return "Medium";
  return "Low";
}

/** `2026-11-02` → `Nov 2, 2026`; anything unreadable is returned as is. */
export function formatPublished(date: string | null | undefined): string | null {
  if (!date) return null;
  const parsed = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return date;
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

export function marketFacts(view: ResearchView): readonly ResearchItem[] {
  return view.items.filter((item) => item.kind === "market_fact");
}

/** Trends and risks: findings that do not need a source. */
export function otherFindings(view: ResearchView): readonly ResearchItem[] {
  return view.items.filter((item) => item.kind === "trend" || item.kind === "risk");
}
