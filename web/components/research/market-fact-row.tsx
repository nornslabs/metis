import { Cite } from "@/components/panel/cite";
import { confidenceLabel, formatPublished, type ResearchItem } from "@/lib/research/view";

/** A market fact: the claim with its source chip, an optional quote, the date and how sure the Researcher is. */
export function MarketFactRow({ item }: { item: ResearchItem }) {
  const published = formatPublished(item.published_at);
  return (
    <li className="flex flex-col gap-1">
      <p className="text-body break-words">
        {item.claim} <Cite url={item.url} />
      </p>
      {item.quote ? (
        <blockquote className="border-l-2 pl-2 text-control break-words text-muted-foreground">{item.quote}</blockquote>
      ) : null}
      <p className="text-meta text-muted-foreground">
        {published ? `${published} · ` : ""}Confidence: {confidenceLabel(item.confidence)}
      </p>
    </li>
  );
}
