import { sourceChips, type ResearchView } from "@/lib/research/view";

/** Square chips under the agent message: a favicon letter and the domain of each source, "+N more". */
export function Sources({ view }: { view: ResearchView }) {
  const { chips, more } = sourceChips(view);
  if (chips.length === 0) return null;
  return (
    <ul aria-label="Sources" className="flex flex-wrap gap-1.5">
      {chips.map((chip) => (
        <li key={chip.domain}>
          <a
            href={chip.href}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="inline-flex items-center gap-1.5 border py-0.5 pr-2 pl-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <span aria-hidden="true" className="grid size-4 place-items-center bg-muted text-micro font-semibold text-foreground">
              {chip.letter}
            </span>
            {chip.domain}
          </a>
        </li>
      ))}
      {more > 0 ? (
        <li className="inline-flex items-center py-0.5 text-xs text-muted-foreground">+{more} more</li>
      ) : null}
    </ul>
  );
}
