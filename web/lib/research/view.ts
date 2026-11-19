import type { components } from "@/lib/api/schema";

export type ResearchView = components["schemas"]["ResearchView"];
export type ResearchItem = ResearchView["items"][number];
export type Competitor = ResearchView["competitors"][number];

export const MAX_SOURCE_CHIPS = 5;
const HIGH_CONFIDENCE = 0.7;
const MEDIUM_CONFIDENCE = 0.4;

export type SourceChip = { readonly domain: string; readonly href: string; readonly letter: string };

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

/** One chip per source domain (competitors first, then sourced items), at most `limit`, and how many were left out. */
export function sourceChips(view: ResearchView, limit = MAX_SOURCE_CHIPS): { chips: SourceChip[]; more: number } {
  const urls = [
    ...view.competitors.map((competitor) => competitor.url),
    ...view.items.filter((item) => item.kind !== "trend" && item.kind !== "risk").map((item) => item.url),
  ];
  const byDomain = new Map<string, SourceChip>();
  for (const url of urls) {
    const domain = domainOf(url);
    const href = safeHref(url);
    if (!domain || !href || byDomain.has(domain)) continue;
    byDomain.set(domain, { domain, href, letter: domain.charAt(0).toUpperCase() });
  }
  const all = [...byDomain.values()];
  return { chips: all.slice(0, limit), more: Math.max(0, all.length - limit) };
}
