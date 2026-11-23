"use client";

import { useRouter } from "next/navigation";
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
import { describeError } from "@/lib/api/errors";
import { useDeleteIdea } from "@/lib/api/mutations/use-delete-idea";

export interface DeleteTarget {
  id: string;
  title: string;
}

interface DeleteIdeaDialogProps {
  target: DeleteTarget | null;
  /** The idea open on the page; deleting it sends the user to the empty page. */
  openIdeaId: string | null;
  onClose: () => void;
}

/** Confirms and archives one idea (`DELETE /v1/ideas/{id}`); leaves the page if it was the open one. */
export function DeleteIdeaDialog({ target, openIdeaId, onClose }: DeleteIdeaDialogProps) {
  const removeIdea = useDeleteIdea();
  const router = useRouter();

  function confirm() {
    if (!target || removeIdea.isPending) return;
    removeIdea.mutate(target.id, {
      onSuccess: () => {
        toast.success("Idea deleted from history");
        if (openIdeaId === target.id) router.replace("/");
        onClose();
      },
      onError: (error) => toast.error(describeError(error)),
    });
  }

  return (
    <AlertDialog
      open={target !== null}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !removeIdea.isPending) onClose();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this idea?</AlertDialogTitle>
          <AlertDialogDescription>
            {target ? `“${target.title}” will be removed from your history.` : "This idea will be removed from your history."}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={removeIdea.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" disabled={removeIdea.isPending} onClick={confirm}>
            {removeIdea.isPending ? "Deleting…" : "Delete idea"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
