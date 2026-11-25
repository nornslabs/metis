"use client";

import { ExternalLink, MoreHorizontal, Trash2 } from "lucide-react";
import Link from "next/link";

import { BAND_SQUARE } from "@/components/history/band-square";
import { ScoreSpark } from "@/components/score/score-spark";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/cn";
import { stageLabel } from "@/lib/events/labels";
import { relativeTime } from "@/lib/history/relative-time";
import { rowLabel, type HistoryRow } from "@/lib/history/rows";

interface IdeaRowProps {
  row: HistoryRow;
  open: boolean;
  onOpen: (event: React.MouseEvent<HTMLAnchorElement>, row: HistoryRow) => void;
  onDelete: (row: HistoryRow) => void;
}

/** One idea in the history list: title, score trend and latest score, stage and time. */
export function IdeaRow({ row, open, onOpen, onDelete }: IdeaRowProps) {
  return (
    <div className="group relative">
      <Link
        href={`/ideas/${row.id}`}
        aria-label={rowLabel(row)}
        aria-current={open ? "page" : undefined}
        title={row.title}
        onClick={(event) => onOpen(event, row)}
        className={cn(
          "relative grid w-full grid-cols-[1fr_auto] gap-x-2 gap-y-0.5 px-3 py-1.75 text-left transition-colors outline-none",
          "hover:bg-accent focus-visible:bg-accent aria-[current=page]:bg-accent",
          "aria-[current=page]:before:absolute aria-[current=page]:before:inset-y-0 aria-[current=page]:before:left-0 aria-[current=page]:before:w-0.5 aria-[current=page]:before:bg-foreground",
        )}
      >
        <span className="truncate text-control font-medium">{row.title}</span>
        <span className="flex items-center gap-1.5 text-note font-semibold tabular-nums">
          <ScoreSpark totals={row.totals} />
          <span aria-hidden="true" className={cn("size-1.5 bg-muted-foreground", row.band && BAND_SQUARE[row.band])} />
          <span className={cn("min-w-4 text-right", row.score === null && "font-normal text-muted-foreground")}>
            {row.score ?? "–"}
          </span>
        </span>
        <span className={cn("col-span-full flex gap-1.5 text-meta text-muted-foreground", row.exportUrl !== null && "pl-17")}>
          {row.exportUrl === null ? (
            <>
              <span>{stageLabel(row.stage)}</span>
              <span aria-hidden="true">·</span>
            </>
          ) : null}
          <span>{relativeTime(row.activeAt)}</span>
        </span>
      </Link>
      {row.exportUrl !== null ? (
        <a
          href={row.exportUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`${row.title} is exported. Open the Linear project`}
          className="absolute bottom-1 left-3 inline-flex h-4 items-center gap-0.5 border px-1 text-meta text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:bg-accent focus-visible:outline-none"
        >
          Exported
          <ExternalLink size={9} aria-hidden="true" />
        </a>
      ) : null}
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label={`Actions for ${row.title}`}
          className={cn(
            "absolute right-1.5 bottom-1 grid size-5 place-items-center text-muted-foreground opacity-0 transition-opacity",
            "group-hover:opacity-100 hover:text-foreground focus-visible:opacity-100 aria-expanded:opacity-100 max-guides:opacity-100",
          )}
        >
          <MoreHorizontal size={13} aria-hidden="true" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={4}>
          <DropdownMenuItem
            className="text-control text-destructive focus:text-destructive"
            onClick={() => onDelete(row)}
          >
            <Trash2 size={13} aria-hidden="true" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
