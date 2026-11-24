"use client";

import { LoadFailure } from "@/components/panel/load-failure";
import { Skeleton } from "@/components/ui/skeleton";
import { useSpecVersion } from "@/lib/api/queries/use-spec-versions";
import { diffSpecs, isUnchanged, type DiffOp, type SectionChange } from "@/lib/spec/diff";

const INSERTED = "bg-success/15 text-success";
const DELETED = "bg-destructive/10 text-destructive line-through";

function Piece({ op }: { op: DiffOp }) {
  if (op.kind === "same") return <>{op.text}</>;
  const inserted = op.kind === "ins";
  const Tag = inserted ? "ins" : "del";
  return (
    <Tag className={inserted ? `${INSERTED} no-underline` : DELETED}>
      <span className="sr-only">{inserted ? "inserted: " : "deleted: "}</span>
      {op.text}
    </Tag>
  );
}

function ChangedBody({ change }: { change: SectionChange }) {
  if (change.kind === "list") {
    return (
      <ul className="flex flex-col gap-0.5 pl-1.5">
        {change.ops.map((op, index) => (
          <li key={index} className="break-words">
            <Piece op={op} />
          </li>
        ))}
      </ul>
    );
  }
  return (
    <p className="break-words">
      {change.ops.map((op, index) => (
        <span key={index}>
          {index > 0 ? " " : ""}
          <Piece op={op} />
        </span>
      ))}
    </p>
  );
}

interface SpecCompareProps {
  ideaId: string;
  /** Older versions to start from (the newest is the other side). */
  fromOptions: readonly number[];
  from: number;
  toNumber: number;
  toMarkdown: string;
  onFrom: (number: number) => void;
}

/** What changed from an older version to the newest, section by section. */
export function SpecCompare({ ideaId, fromOptions, from, toNumber, toMarkdown, onFrom }: SpecCompareProps) {
  const query = useSpecVersion(ideaId, from);
  const diff = query.data === undefined ? null : diffSpecs(query.data.content_md, toMarkdown);

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-control">
        <label className="flex items-center gap-1.5">
          From
          <select
            value={from}
            className="h-7 border border-border bg-card px-1.5 text-control"
            onChange={(event) => onFrom(Number(event.target.value))}
          >
            {fromOptions.map((number) => (
              <option key={number} value={number}>{`v${number}`}</option>
            ))}
          </select>
        </label>
        <span aria-hidden="true">→</span>
        <span>{`v${toNumber}`}</span>
        {diff ? (
          <span className="ml-auto text-meta text-muted-foreground">
            <span className="text-success">{`${diff.inserted} added`}</span>
            {" · "}
            <span className="text-destructive">{`${diff.deleted} removed`}</span>
          </span>
        ) : null}
      </div>
      {query.isError ? <LoadFailure what={`spec v${from}`} error={query.error} onRetry={() => void query.refetch()} /> : null}
      {query.isPending ? <Skeleton className="h-32 w-full" /> : null}
      {diff?.sections.map((change) => (
        <section key={change.key} aria-label={`${change.label}, changes`} className="mb-3.5 text-control last:mb-0">
          <h4 className="mb-1 text-control font-semibold">
            {change.label}
            {isUnchanged(change) ? <span className="ml-2 font-normal text-muted-foreground">No changes</span> : null}
          </h4>
          {isUnchanged(change) ? null : <ChangedBody change={change} />}
        </section>
      ))}
    </>
  );
}
