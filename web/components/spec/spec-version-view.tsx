"use client";

import { LoadFailure } from "@/components/panel/load-failure";
import { ListField, TextField } from "@/components/spec/spec-fields";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSpecVersion } from "@/lib/api/queries/use-spec-versions";
import { visibleSections } from "@/lib/spec/sections";
import { sourceLabel } from "@/lib/spec/view";

const NOTHING = () => undefined;

interface SpecVersionViewProps {
  ideaId: string;
  number: number;
  latestNumber: number;
  /** The newest version's text: restoring a version that equals it does nothing. */
  latestMarkdown: string;
  /** False once the spec is confirmed: nothing can be restored. */
  canRestore: boolean;
  onBack: () => void;
  onRestore: (contentMd: string) => void;
}

/** An older version, read-only, with Back and Restore. */
export function SpecVersionView({ ideaId, number, latestNumber, latestMarkdown, canRestore, onBack, onRestore }: SpecVersionViewProps) {
  const query = useSpecVersion(ideaId, number);
  if (query.isError) return <LoadFailure what={`spec v${number}`} error={query.error} onRetry={() => void query.refetch()} />;
  if (query.data === undefined) return <Skeleton className="h-32 w-full" />;

  const version = query.data;
  const same = version.content_md === latestMarkdown;
  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2 border border-border bg-card px-2.5 py-2 text-control">
        <span className="min-w-0 flex-1">
          Viewing <b className="font-medium">{`v${number}`}</b>
          {` by ${sourceLabel(version.source)}, read-only.`}
        </span>
        <Button type="button" variant="outline" size="sm" onClick={onBack}>
          {`Back to v${latestNumber}`}
        </Button>
        {canRestore ? (
          <Button
            type="button"
            size="sm"
            disabled={same}
            title={same ? `Same as v${latestNumber}` : undefined}
            onClick={() => onRestore(version.content_md)}
          >
            {`Restore as v${latestNumber + 1}`}
          </Button>
        ) : null}
      </div>
      {visibleSections(version.content_md).map((view) => (
        <section key={`${number}:${view.key}`} aria-label={`${view.label}, v${number}`} className="mb-3.5 last:mb-0">
          <h4 className="mb-1 text-control font-semibold">{view.label}</h4>
          {view.kind === "list" ? (
            <ListField label={view.label} placeholder="" locked initial={view.items} onChange={NOTHING} />
          ) : (
            <TextField label={view.label} placeholder="" locked initial={view.text} onChange={NOTHING} />
          )}
        </section>
      ))}
    </>
  );
}
