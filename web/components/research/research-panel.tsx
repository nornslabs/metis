import type { ReactNode } from "react";

import { CompetitorCard } from "@/components/research/competitor-card";
import { MarketFactRow } from "@/components/research/market-fact-row";
import { marketFacts, otherFindings, type ResearchView } from "@/lib/research/view";

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="flex flex-col gap-1.5">
      <h3 className="text-meta font-medium text-muted-foreground uppercase tracking-label">{title}</h3>
      <ul className="flex flex-col gap-1.5">{children}</ul>
    </section>
  );
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** The research in a collapsible block inside the agent message (ui-context.md, Research). */
export function ResearchPanel({ view }: { view: ResearchView }) {
  const facts = marketFacts(view);
  const others = otherFindings(view);
  return (
    <details open className="group border">
      <summary className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-control font-medium select-none">
        Research
        <span className="font-normal text-meta text-muted-foreground">
          {plural(view.competitors.length, "competitor")} · {plural(facts.length, "fact")}
        </span>
      </summary>
      <div className="flex flex-col gap-3 border-t px-2.5 py-2">
        {view.summary ? <p className="text-body break-words whitespace-pre-wrap">{view.summary}</p> : null}
        {view.competitors.length > 0 ? (
          <Group title="Competitors">
            {view.competitors.map((competitor) => (
              <CompetitorCard key={competitor.id} competitor={competitor} />
            ))}
          </Group>
        ) : null}
        {facts.length > 0 ? (
          <Group title="Market facts">
            {facts.map((item) => (
              <MarketFactRow key={item.id} item={item} />
            ))}
          </Group>
        ) : null}
        {others.length > 0 ? (
          <Group title="Trends and risks">
            {others.map((item) => (
              <li key={item.id} className="border px-2.5 py-2 text-body break-words">
                <span className="mr-2 font-mono text-meta text-muted-foreground uppercase">{item.kind}</span>
                {item.claim}
              </li>
            ))}
          </Group>
        ) : null}
        {view.competitors.length === 0 && facts.length === 0 && others.length === 0 ? (
          <p className="text-control text-muted-foreground">The Researcher found nothing to show.</p>
        ) : null}
      </div>
    </details>
  );
}
