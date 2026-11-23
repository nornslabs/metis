import { deltaText, type ScoreVersion } from "@/lib/scores/versions";
import {
  BAND_LABELS,
  MAX_RAW,
  MAX_TOTAL,
  PARAM_LABELS,
  SUGGESTION_KIND_LABELS,
  formatDay,
  formatPoints,
  type ScoreRun,
  type Suggestion,
} from "@/lib/scores/view";
import { confidenceLabel, safeHref } from "@/lib/research/view";

export interface ScoreReportInput {
  ideaTitle: string;
  score: ScoreRun;
  versions: readonly ScoreVersion[];
  /** The newest score run's suggestions. */
  suggestions: readonly Suggestion[];
}

const FALLBACK_SLUG = "idea";
const SLUG_LIMIT = 40;

/** A link for an http(s) URL, else the plain title: evidence from a model is never trusted. */
function link(title: string, url: string): string {
  return safeHref(url) !== null ? `[${line(title)}](${url})` : line(title);
}

function line(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function paramSection(param: ScoreRun["params"][number]): string {
  const evidence =
    param.no_evidence || param.evidence.length === 0
      ? ["- No evidence: this mark is a guess."]
      : param.evidence.map((item) => `- ${link(item.title, item.url)}${item.quote ? ` — “${line(item.quote)}”` : ""}`);
  return [
    `### ${PARAM_LABELS[param.param]} — ${param.raw}/${MAX_RAW} (${formatPoints(param.weighted)} of ${param.weight} points)`,
    "",
    line(param.reason),
    "",
    `Confidence: ${confidenceLabel(param.confidence)} (${param.confidence.toFixed(2)})`,
    "",
    ...evidence,
  ].join("\n");
}

function suggestionSection(suggestion: Suggestion): string {
  const sources = suggestion.evidence.map((item) => link(item.title, item.url)).join(", ");
  return [
    `- **${SUGGESTION_KIND_LABELS[suggestion.kind]}: ${line(suggestion.title)}** — ${line(suggestion.rationale)}`,
    suggestion.expected_impact ? `  - Expected impact: ${line(suggestion.expected_impact)}` : null,
    sources ? `  - Sources: ${sources}` : null,
  ]
    .filter((row): row is string => row !== null)
    .join("\n");
}

/** The score as a Markdown report: verdict, six parameters with reasons and evidence, history, suggestions. */
export function buildScoreReport({ ideaTitle, score, versions, suggestions }: ScoreReportInput): string {
  const current = versions.find((version) => version.id === score.id);
  const delta = current ? deltaText(current.delta) : null;
  const history = versions.map(
    (version) => `- v${version.number}: ${version.total} (${BAND_LABELS[version.band]}), ${formatDay(version.createdAt)} — ${version.note}`,
  );
  const blocks = [
    `# ${line(ideaTitle) || "Idea"}: score report`,
    `**${score.total} / ${MAX_TOTAL}** · ${BAND_LABELS[score.band]}${current ? ` · v${current.number}` : ""}${delta ? ` · ${delta}` : ""}`,
    `Scored ${formatDay(score.created_at)}.`,
    "## Parameters",
    ...score.params.map(paramSection),
    history.length > 1 ? ["## History", ...history].join("\n\n") : null,
    suggestions.length > 0 ? ["## Suggestions", ...suggestions.map(suggestionSection)].join("\n\n") : null,
  ];
  return `${blocks.filter((block): block is string => block !== null).join("\n\n")}\n`;
}

/** `metis-<idea title as a slug>-score.md`. */
export function reportFileName(ideaTitle: string): string {
  const slug = ideaTitle
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, SLUG_LIMIT)
    .replace(/-+$/g, "");
  return `metis-${slug || FALLBACK_SLUG}-score.md`;
}
