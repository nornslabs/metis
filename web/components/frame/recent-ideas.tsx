"use client";

import { History, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { describeError } from "@/lib/api/errors";
import { useDeleteIdea } from "@/lib/api/mutations/use-delete-idea";
import { useIdeas } from "@/lib/api/queries/use-ideas";
import { stageLabel } from "@/lib/events/labels";
import { cn } from "@/lib/utils";

type IdeaHistoryItem = { id: string; title: string };

function IdeaItems({ onDelete }: { onDelete: (idea: IdeaHistoryItem) => void }) {
  const ideas = useIdeas();
  if (ideas.isPending) {
    return (
      <div aria-busy="true" className="flex flex-col gap-1.5 p-2">
        <Skeleton className="h-3 w-4/5" />
        <Skeleton className="h-3 w-3/5" />
      </div>
    );
  }
  if (ideas.isError) {
    return <p className="p-2 text-note text-destructive">{describeError(ideas.error)}</p>;
  }

  const items = ideas.data.pages.flatMap((page) => page.items);
  if (items.length === 0) {
    return <p className="p-2 text-control text-muted-foreground">No ideas yet</p>;
  }

  return (
    <>
      {items.map((idea) => (
        <div key={idea.id} role="group" aria-label={`${idea.title} actions`} className="flex gap-0.5">
          <DropdownMenuItem
            className="h-7 min-w-0 flex-1 justify-between gap-3 text-control"
            render={<Link href={`/ideas/${idea.id}`} />}
          >
            <span className="truncate">{idea.title}</span>
            <span className="shrink-0 text-meta text-muted-foreground">
              {stageLabel(idea.stage)}
            </span>
          </DropdownMenuItem>
          <Button
            variant="ghost"
            size="xs"
            className="h-7 shrink-0 gap-1 px-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive"
            aria-label={`Delete ${idea.title} from chat history`}
            title="Delete chat"
            type="button"
            onClick={() => onDelete({ id: idea.id, title: idea.title })}
          >
            <Trash2 size={14} aria-hidden="true" />
          </Button>
        </div>
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

/** Header popover listing workspace ideas, newest first, to reopen or delete one. */
export function RecentIdeas() {
  const [open, setOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<IdeaHistoryItem | null>(null);
  const removeIdea = useDeleteIdea();
  const router = useRouter();

  function requestDelete(idea: IdeaHistoryItem) {
    setOpen(false);
    setDeleteTarget(idea);
  }

  function deleteSelectedIdea() {
    if (!deleteTarget || removeIdea.isPending) return;

    removeIdea.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success("Chat deleted from history");
        if (window.location.pathname === `/ideas/${deleteTarget.id}`) router.replace("/");
        setDeleteTarget(null);
      },
      onError: (error) => toast.error(describeError(error)),
    });
  }

  return (
    <>
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
            {open ? <IdeaItems onDelete={requestDelete} /> : null}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !removeIdea.isPending) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this chat?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget
                ? `“${deleteTarget.title}” will be removed from your chat history.`
                : "This chat will be removed from your history."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={removeIdea.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={removeIdea.isPending}
              onClick={deleteSelectedIdea}
            >
              {removeIdea.isPending ? "Deleting…" : "Delete chat"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
