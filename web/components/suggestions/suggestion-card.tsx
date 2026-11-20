import { Button } from "@/components/ui/button";
import { SourceLink } from "@/components/research/source-link";
import { PARAM_LABELS, SUGGESTION_KIND_LABELS, type Suggestion } from "@/lib/scores/view";

interface SuggestionCardProps {
  suggestion: Suggestion;
  disabled: boolean;
  onStatus: (status: Suggestion["status"]) => void;
}

/** One improvement idea: kind, rationale, the parameters it lifts, its sources, and Accept / Dismiss. */
export function SuggestionCard({ suggestion, disabled, onStatus }: SuggestionCardProps) {
  const { status } = suggestion;
  return (
    <li className="flex flex-col gap-1.5 border px-2.5 py-2">
      <div className="flex items-center gap-2">
        <span className="inline-flex h-badge items-center bg-secondary px-2 text-micro font-medium uppercase tracking-label">
          {SUGGESTION_KIND_LABELS[suggestion.kind]}
        </span>
        <h4 className="text-body font-medium break-words">{suggestion.title}</h4>
      </div>
      <p className="text-control break-words whitespace-pre-wrap">{suggestion.rationale}</p>
      <p className="text-meta text-muted-foreground">
        Lifts: {suggestion.target_params.map((param) => PARAM_LABELS[param]).join(", ")}
      </p>
      {suggestion.expected_impact ? (
        <p className="text-meta break-words text-muted-foreground">Expected impact: {suggestion.expected_impact}</p>
      ) : null}
      <ul className="flex flex-wrap gap-x-3 gap-y-0.5">
        {suggestion.evidence.map((item) => (
          <li key={`${item.url}:${item.title}`}>
            <SourceLink url={item.url} />
          </li>
        ))}
      </ul>
      <div className="flex items-center gap-1.5">
        {status === "open" ? (
          <>
            <Button type="button" size="sm" disabled={disabled} onClick={() => onStatus("accepted")}>
              Accept
            </Button>
            <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => onStatus("dismissed")}>
              Dismiss
            </Button>
          </>
        ) : (
          <>
            <span className="text-control font-medium">{status === "accepted" ? "Accepted" : "Dismissed"}</span>
            <Button type="button" variant="ghost" size="sm" disabled={disabled} onClick={() => onStatus("open")}>
              Undo
            </Button>
          </>
        )}
      </div>
    </li>
  );
}
