import { SourceLink } from "@/components/research/source-link";
import { confidenceLabel, formatPublished, type ResearchItem } from "@/lib/research/view";

/** A market fact: the claim, its quote, a source link, the date and how sure the Researcher is. */
export function MarketFactRow({ item }: { item: ResearchItem }) {
  const published = formatPublished(item.published_at);
  return (
    <li className="flex flex-col gap-1 border px-2.5 py-2">
      <p className="text-body break-words">{item.claim}</p>
      {item.quote ? (
        <blockquote className="border-l-2 pl-2 text-control break-words text-muted-foreground">{item.quote}</blockquote>
      ) : null}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-meta text-muted-foreground">
        <SourceLink url={item.url} />
        {published ? <span>{published}</span> : null}
        <span>Confidence: {confidenceLabel(item.confidence)}</span>
      </div>
    </li>
  );
}
