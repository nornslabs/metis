"use client";

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

interface ConfirmSpecDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  number: number;
  onConfirm: () => void;
}

/** "Confirm spec vN?": what confirming does, with Cancel and a primary confirm. */
export function ConfirmSpecDialog({ open, onOpenChange, number, onConfirm }: ConfirmSpecDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{`Confirm spec v${number}?`}</AlertDialogTitle>
          <AlertDialogDescription>Metis will plan the phases from this version. You can&apos;t edit it after this.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{`Confirm v${number}`}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
