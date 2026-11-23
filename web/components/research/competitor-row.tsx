import { Cite } from "@/components/panel/cite";
import { competitorRelation, domainOf, overlapPercent, type Competitor } from "@/lib/research/view";

/** A competitor: letter mark, name with its source chip, one line, domain and a Direct or Adjacent tag. */
export function CompetitorRow({ competitor }: { competitor: Competitor }) {
  const domain = domainOf(competitor.url);
  const relation = competitorRelation(competitor.overlap);
  const letter = (domain ?? competitor.name).charAt(0).toUpperCase();
  return (
    <li className="flex items-start gap-2.5">
      <span aria-hidden="true" className="grid size-4.5 shrink-0 place-items-center bg-muted text-micro font-semibold">
        {letter}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <p className="text-body font-medium break-words">
          {competitor.name} <Cite url={competitor.url} />
        </p>
        {competitor.description ? <p className="text-control break-words text-muted-foreground">{competitor.description}</p> : null}
        <p className="text-meta text-muted-foreground">
          {domain ?? "No source"}
          {competitor.pricing ? ` · ${competitor.pricing}` : ""}
        </p>
      </div>
      <span
        title={`Overlap ${overlapPercent(competitor.overlap)}`}
        className="shrink-0 border px-1.5 py-px text-micro font-medium text-muted-foreground"
      >
        {relation}
        <span className="sr-only"> (overlap {overlapPercent(competitor.overlap)})</span>
      </span>
    </li>
  );
}
