import type { components } from "@/lib/api/schema";

export type ScoreRun = components["schemas"]["ScoreRun"];
export type ScoreRunSummary = components["schemas"]["ScoreRunSummary"];
export type ScoreParamResult = components["schemas"]["ScoreParamResult"];
export type ScoreParam = components["schemas"]["ScoreParam"];
export type ScoreBand = components["schemas"]["ScoreBand"];
export type Suggestion = components["schemas"]["Suggestion"];
export type SuggestionKind = components["schemas"]["SuggestionKind"];

/** Highest mark a parameter can get. */
export const MAX_RAW = 10;
/** Band thresholds from the rubric: `build` from 75, `promising` from 55, `advise` below. */
export const BUILD_FROM = 75;
export const PROMISING_FROM = 55;
export const MAX_TOTAL = 100;

const MS_PER_DAY = 86_400_000;

export const PARAM_LABELS: Readonly<Record<ScoreParam, string>> = {
  problem_severity: "Problem severity",
  uniqueness: "Uniqueness",
  market_demand: "Market demand",
  value: "Value",
  feasibility: "Feasibility",
  timing: "Timing",
};

export const BAND_LABELS: Readonly<Record<ScoreBand, string>> = {
  build: "Build",
  promising: "Promising",
  advise: "Advise",
};

export const SUGGESTION_KIND_LABELS: Readonly<Record<SuggestionKind, string>> = {
  feature: "Feature",
  niche: "Niche",
  pricing: "Pricing",
  pivot: "Pivot",
};

/** The band's threshold text shown beside its label. */
export const BAND_RANGES: Readonly<Record<ScoreBand, string>> = {
  build: "75+",
  promising: "55–74",
  advise: "below 55",
};

/** "today", "1 day ago", "N days ago": how long ago a score was made. */
export function daysAgoLabel(iso: string, now: Date = new Date()): string {
  const created = new Date(iso).getTime();
  if (Number.isNaN(created)) return "";
  const days = Math.floor((now.getTime() - created) / MS_PER_DAY);
  if (days < 1) return "today";
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

const MS_PER_MINUTE = 60_000;
const MINUTES_PER_HOUR = 60;

/** "just now", "5 min ago", "3 h ago", then days: how long ago something was updated. */
export function updatedAgoLabel(iso: string, now: Date = new Date()): string {
  const created = new Date(iso).getTime();
  if (Number.isNaN(created)) return "";
  const minutes = Math.floor((now.getTime() - created) / MS_PER_MINUTE);
  if (minutes < 1) return "just now";
  if (minutes < MINUTES_PER_HOUR) return `${minutes} min ago`;
  const hours = Math.floor(minutes / MINUTES_PER_HOUR);
  return hours < 24 ? `${hours} h ago` : daysAgoLabel(iso, now);
}

/** `2026-11-20T10:00:00Z` → `Nov 20, 2026`. */
export function formatDay(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

/** A raw mark as a width: `7` → `70%`. */
export function barPercent(raw: number): number {
  return Math.min(MAX_RAW, Math.max(0, raw)) * (100 / MAX_RAW);
}

/** `weighted` is points out of the weight: `17.5` → `17.5`, `18` → `18`. */
export function formatPoints(points: number): string {
  return Number.isInteger(points) ? String(points) : points.toFixed(1);
}

export type ChartPoint = {
  readonly id: string;
  readonly total: number;
  readonly band: ScoreBand;
  readonly createdAt: string;
  readonly trigger: string;
  /** 0–100, left to right, oldest first. */
  readonly x: number;
  /** 0–100, top to bottom: a total of 100 is at the top. */
  readonly y: number;
};

/** The history (newest first, as the server sends it) as chart points, oldest first. */
export function chartPoints(history: readonly ScoreRunSummary[]): readonly ChartPoint[] {
  const ordered = [...history].reverse();
  const last = Math.max(ordered.length - 1, 1);
  return ordered.map((run, index) => ({
    id: run.id,
    total: run.total,
    band: run.band,
    createdAt: run.created_at,
    trigger: run.trigger,
    x: ordered.length === 1 ? 50 : (index / last) * 100,
    y: MAX_TOTAL - Math.min(MAX_TOTAL, Math.max(0, run.total)),
  }));
}

/** Suggestions grouped by score run, in the order the server sent them (newest run first). */
export function groupByScoreRun(suggestions: readonly Suggestion[]): readonly (readonly Suggestion[])[] {
  const groups = new Map<string, Suggestion[]>();
  for (const suggestion of suggestions) {
    groups.set(suggestion.score_run_id, [...(groups.get(suggestion.score_run_id) ?? []), suggestion]);
  }
  return [...groups.values()];
}
