"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { toast } from "sonner";

import { DeleteIdeaDialog, type DeleteTarget } from "@/components/history/delete-idea-dialog";
import { HistoryFilters } from "@/components/history/history-filters";
import { HistorySearch } from "@/components/history/history-search";
import { IdeaRow } from "@/components/history/idea-row";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { describeError } from "@/lib/api/errors";
import { useIdeas, type IdeaFilter } from "@/lib/api/queries/use-ideas";
import { useScoreSummaries } from "@/lib/api/queries/use-score-summaries";
import { groupByActivity } from "@/lib/history/group";
import { toHistoryRow, type HistoryRow } from "@/lib/history/rows";
import { useDebouncedValue } from "@/lib/history/use-debounced-value";
import { useBusyIdeaId } from "@/lib/workspace/run-activity";
import { useNarrow } from "@/lib/workspace/use-narrow";
import { useWorkspacePanels } from "@/lib/workspace/workspace-panels";

const SEARCH_DEBOUNCE_MS = 250;
const SWITCH_BLOCKED = "Metis is working on this idea. Stop the run or wait.";

function isPlainLeftClick(event: MouseEvent): boolean {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

/** Calls `onReach` when the sentinel scrolls into view inside `root`. */
function useReachEnd(root: React.RefObject<HTMLElement | null>, enabled: boolean, onReach: () => void) {
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const target = sentinel.current;
    if (!enabled || !target) return;
    const observer = new IntersectionObserver((entries) => entries[0]?.isIntersecting && onReach(), {
      root: root.current,
    });
    observer.observe(target);
    return () => observer.disconnect();
  }, [enabled, onReach, root]);
  return sentinel;
}

function ListMessage({ children }: { children: React.ReactNode }) {
  return <p className="px-3 py-6 text-center text-control text-muted-foreground">{children}</p>;
}

/** Search, filters, the grouped list and the footer of the history panel. */
export function HistoryList() {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<IdeaFilter>("all");
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const q = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const ideas = useIdeas({ q, filter });
  const loaded = useMemo(() => ideas.data?.pages.flatMap((page) => page.items) ?? [], [ideas.data]);
  const summaries = useScoreSummaries(loaded.map((idea) => idea.id));
  const rows = useMemo(() => loaded.map((idea) => toHistoryRow(idea, summaries.get(idea.id))), [loaded, summaries]);
  const groups = useMemo(() => groupByActivity(rows), [rows]);

  const { searchRef, closeHistory } = useWorkspacePanels();
  const openIdeaId = useParams<{ ideaId?: string }>().ideaId ?? null;
  const busyIdeaId = useBusyIdeaId();
  const narrow = useNarrow();
  const listRef = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = ideas;
  const sentinel = useReachEnd(listRef, hasNextPage && !isFetchingNextPage, () => void fetchNextPage());

  function openIdea(event: MouseEvent<HTMLAnchorElement>, row: HistoryRow) {
    if (!isPlainLeftClick(event)) return;
    if (row.id === openIdeaId) {
      event.preventDefault();
      return;
    }
    if (busyIdeaId !== null) {
      event.preventDefault();
      toast(SWITCH_BLOCKED);
      return;
    }
    if (narrow) closeHistory();
  }

  const filtering = q !== "" || filter !== "all";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <HistorySearch value={search} onChange={setSearch} inputRef={searchRef} />
      <HistoryFilters value={filter} onChange={setFilter} />
      <div ref={listRef} aria-busy={ideas.isFetching} className="min-h-0 flex-1 overflow-y-auto pt-1 pb-2">
        {ideas.isPending ? (
          <div className="flex flex-col gap-2.5 px-3 py-2">
            <Skeleton className="h-3 w-4/5" />
            <Skeleton className="h-3 w-3/5" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        ) : ideas.isError ? (
          <div className="flex flex-col items-center gap-2 px-3 py-6">
            <p className="text-center text-note text-destructive">{describeError(ideas.error)}</p>
            <Button type="button" variant="outline" size="xs" onClick={() => void ideas.refetch()}>
              Retry
            </Button>
          </div>
        ) : rows.length === 0 ? (
          <ListMessage>{filtering ? "No ideas match." : "No ideas yet."}</ListMessage>
        ) : (
          groups.map(({ group, rows: groupRows }) => (
            <section key={group} aria-label={group}>
              <h3 className="px-3 pt-2.5 pb-1 text-meta font-medium tracking-label text-muted-foreground uppercase">
                {group}
              </h3>
              {groupRows.map((row) => (
                <IdeaRow
                  key={row.id}
                  row={row}
                  open={row.id === openIdeaId}
                  onOpen={openIdea}
                  onDelete={setDeleteTarget}
                />
              ))}
            </section>
          ))
        )}
        <div ref={sentinel} aria-hidden="true" className="h-px" />
        {isFetchingNextPage ? <ListMessage>Loading…</ListMessage> : null}
      </div>
      <div className="flex shrink-0 justify-between border-t px-3 py-2 text-meta text-muted-foreground">
        <span>{`${rows.length}${hasNextPage ? "+" : ""} ${rows.length === 1 ? "idea" : "ideas"}`}</span>
        <span>Sorted by last activity</span>
      </div>
      <DeleteIdeaDialog target={deleteTarget} openIdeaId={openIdeaId} onClose={() => setDeleteTarget(null)} />
    </div>
  );
}
