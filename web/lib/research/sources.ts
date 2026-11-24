import { domainOf, safeHref, type ResearchView } from "@/lib/research/view";

/** One numbered source: the page a claim or a rubric reason points to. */
export interface SourceEntry {
  readonly number: number;
  readonly href: string;
  readonly domain: string;
  readonly title: string;
}

/** A page the Scorer cited for a rubric parameter. */
export interface EvidenceSource {
  readonly url: string;
  readonly title: string;
}

export interface SourceIndex {
  readonly entries: readonly SourceEntry[];
  /** The number of the source for `url`, or null when it is not a listed http(s) page. */
  numberFor: (url: string | null | undefined) => number | null;
  /** The listed source for `url`, or undefined. */
  entryFor: (url: string | null | undefined) => SourceEntry | undefined;
}

/** The same page under one key: no `#fragment`, no trailing `/` (the server's SourceBook rule). */
export function normalizeSourceUrl(url: string | null | undefined): string | null {
  const href = safeHref(url);
  if (href === null) return null;
  const parsed = new URL(href);
  parsed.hash = "";
  return parsed.href.replace(/\/+$/, "");
}

interface Candidate {
  readonly url: string | null;
  readonly title: string;
}

function candidatesOf(view: ResearchView | null, evidence: readonly EvidenceSource[]): readonly Candidate[] {
  const competitors = (view?.competitors ?? []).map((competitor) => ({ url: competitor.url, title: competitor.name }));
  // Trends and risks need no source, so they are never listed.
  const items = (view?.items ?? [])
    .filter((item) => item.kind !== "trend" && item.kind !== "risk")
    .map((item) => ({ url: item.url, title: item.title }));
  return [...competitors, ...items, ...evidence];
}

/**
 * The numbered Sources list: competitors (server order), then research items, then the Scorer's
 * evidence pages that are not already listed. First seen wins, so a number never moves, and one
 * page has one number however its URL is spelled.
 */
export function buildSourceIndex(view: ResearchView | null, evidence: readonly EvidenceSource[] = []): SourceIndex {
  const entries: SourceEntry[] = [];
  const numbers = new Map<string, number>();
  for (const candidate of candidatesOf(view, evidence)) {
    const key = normalizeSourceUrl(candidate.url);
    const href = safeHref(candidate.url);
    const domain = domainOf(candidate.url);
    if (key === null || href === null || domain === null || numbers.has(key)) continue;
    const number = entries.length + 1;
    numbers.set(key, number);
    entries.push({ number, href, domain, title: candidate.title.trim() || domain });
  }
  const numberFor = (url: string | null | undefined) => numbers.get(normalizeSourceUrl(url) ?? "") ?? null;
  return { entries, numberFor, entryFor: (url) => entries[(numberFor(url) ?? 0) - 1] };
}

/** The pages cited by a score's parameters, in parameter order; a "no evidence" parameter cites none. */
export function evidenceSources(
  params: readonly { readonly no_evidence: boolean; readonly evidence: readonly EvidenceSource[] }[],
): readonly EvidenceSource[] {
  return params.flatMap((param) => (param.no_evidence ? [] : param.evidence.map(({ url, title }) => ({ url, title }))));
}
