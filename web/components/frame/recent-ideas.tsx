"use client";

import { History } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { describeError } from "@/lib/api/errors";
import { useIdeas } from "@/lib/api/queries/use-ideas";
import { stageLabel } from "@/lib/events/labels";
import { cn } from "@/lib/utils";

function IdeaItems() {
  const ideas = useIdeas();
  if (ideas.isPending) {
    return (
      <div aria-busy="true" className="flex flex-col gap-1.5 p-2">
        <Skeleton className="h-3 w-4/5" />
        <Skeleton className="h-3 w-3/5" />
      </div>
    );
  }
  if (ideas.isError) return <p className="p-2 text-note text-destructive">{describeError(ideas.error)}</p>;

  const items = ideas.data.pages.flatMap((page) => page.items);
  if (items.length === 0) return <p className="p-2 text-control text-muted-foreground">No ideas yet</p>;

  return (
    <>
      {items.map((idea) => (
        <DropdownMenuItem
          key={idea.id}
          className="h-7 justify-between gap-3 text-control"
          render={<Link href={`/ideas/${idea.id}`} />}
        >
          <span className="truncate">{idea.title}</span>
          <span className="shrink-0 text-meta text-muted-foreground">{stageLabel(idea.stage)}</span>
        </DropdownMenuItem>
      ))}
      {ideas.hasNextPage ? (
        <DropdownMenuItem
          closeOnClick={false}
          disabled={ideas.isFetchingNextPage}
          className="h-7 text-control text-muted-foreground"
          onClick={() => void ideas.fetchNextPage()}
        >
          {ideas.isFetchingNextPage ? "Loading…" : "Load more"}
        </DropdownMenuItem>
      ) : null}
    </>
  );
}

/** Header popover listing the workspace's ideas, newest first, to reopen one (ui-context.md, AppHeader). */
export function RecentIdeas() {
  const [open, setOpen] = useState(false);
  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <Tooltip>
        <TooltipTrigger
          render={
            <DropdownMenuTrigger
              aria-label="Recent ideas"
              className={cn(buttonVariants({ variant: "ghost", size: "icon-sm" }))}
            />
          }
        >
          <History size={15} strokeWidth={2} />
        </TooltipTrigger>
        <TooltipContent>Recent ideas</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end" sideOffset={6} className="w-59 p-0.5">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-meta font-medium tracking-label text-muted-foreground uppercase">
            Recent ideas
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {/* Mounted only while open, so the list loads when it is first needed. */}
          {open ? <IdeaItems /> : null}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
