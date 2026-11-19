import { SourceLink } from "@/components/research/source-link";
import { domainOf, overlapPercent, safeHref, type Competitor } from "@/lib/research/view";

/** A competitor: favicon letter, name as a link, what it does, pricing and how much it overlaps. */
export function CompetitorCard({ competitor }: { competitor: Competitor }) {
  const href = safeHref(competitor.url);
  const letter = (domainOf(competitor.url) ?? competitor.name).charAt(0).toUpperCase();
  return (
    <li className="flex flex-col gap-1 border px-2.5 py-2">
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className="grid size-4.5 shrink-0 place-items-center bg-muted text-micro font-semibold">
          {letter}
        </span>
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="min-w-0 truncate text-body font-medium underline underline-offset-2"
          >
            {competitor.name}
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        ) : (
          <span className="min-w-0 truncate text-body font-medium">{competitor.name}</span>
        )}
        <span className="ml-auto shrink-0 font-mono text-meta text-muted-foreground">
          Overlap {overlapPercent(competitor.overlap)}
        </span>
      </div>
      {competitor.description ? <p className="text-control break-words">{competitor.description}</p> : null}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-meta text-muted-foreground">
        {competitor.pricing ? <span>Pricing: {competitor.pricing}</span> : null}
        <SourceLink url={competitor.url} />
      </div>
    </li>
  );
}
