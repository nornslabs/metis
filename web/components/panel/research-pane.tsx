"use client";

import { Download } from "lucide-react";

import { PaneFooter } from "@/components/panel/pane-footer";
import { PaneSection } from "@/components/panel/pane-section";
import { CompetitorRow } from "@/components/research/competitor-row";
import { MarketFactRow } from "@/components/research/market-fact-row";
import { SourceRow } from "@/components/research/source-row";
import { Button } from "@/components/ui/button";
import { downloadTextFile } from "@/lib/download";
import { buildSourcesReport, sourcesFileName } from "@/lib/research/sources-report";
import type { SourceEntry } from "@/lib/research/sources";
import { useSourceIndex } from "@/lib/research/source-context";
import { marketFacts, otherFindings, type ResearchView } from "@/lib/research/view";
import { countOf } from "@/lib/text/count";

/** The Research pane's body: competitors and market facts with source chips, then the numbered Sources. */
export function ResearchPaneBody({ view }: { view: ResearchView }) {
  const { entries } = useSourceIndex();
  const facts = marketFacts(view);
  const others = otherFindings(view);
  const empty = view.competitors.length === 0 && facts.length === 0 && others.length === 0;
  return (
    <>
      {view.summary ? (
        <p className="border-b px-4 py-3.5 text-body break-words whitespace-pre-wrap">{view.summary}</p>
      ) : null}
      {view.competitors.length > 0 ? (
        <PaneSection heading="Competitors" aside={String(view.competitors.length)}>
          <ul className="flex flex-col gap-3">
            {view.competitors.map((competitor) => (
              <CompetitorRow key={competitor.id} competitor={competitor} />
            ))}
          </ul>
        </PaneSection>
      ) : null}
      {facts.length > 0 ? (
        <PaneSection heading="Market facts" aside={String(facts.length)}>
          <ul className="flex flex-col gap-3">
            {facts.map((item) => (
              <MarketFactRow key={item.id} item={item} />
            ))}
          </ul>
        </PaneSection>
      ) : null}
      {others.length > 0 ? (
        <PaneSection heading="Trends and risks" aside={String(others.length)}>
          <ul className="flex flex-col gap-2">
            {others.map((item) => (
              <li key={item.id} className="text-body break-words">
                <span className="mr-2 font-mono text-meta text-muted-foreground uppercase">{item.kind}</span>
                {item.claim}
              </li>
            ))}
          </ul>
        </PaneSection>
      ) : null}
      {empty ? <p className="px-4 py-3.5 text-control text-muted-foreground">The Researcher found nothing to show.</p> : null}
      {entries.length > 0 ? (
        <PaneSection heading="Sources" aside={String(entries.length)}>
          <ol aria-label="Sources" className="flex flex-col">
            {entries.map((entry) => (
              <SourceRow key={entry.number} entry={entry} />
            ))}
          </ol>
        </PaneSection>
      ) : null}
    </>
  );
}

/** The Research pane's footer: Export sources and the source count. */
export function ResearchPaneFooter({ ideaTitle, entries }: { ideaTitle: string; entries: readonly SourceEntry[] }) {
  return (
    <PaneFooter meta={`${countOf(entries.length, "source")} via Exa`}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={entries.length === 0}
        onClick={() => downloadTextFile(sourcesFileName(ideaTitle), buildSourcesReport(ideaTitle, entries))}
      >
        <Download size={13} aria-hidden="true" />
        Export sources
      </Button>
    </PaneFooter>
  );
}
