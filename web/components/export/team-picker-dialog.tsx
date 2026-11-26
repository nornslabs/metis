"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/cn";
import type { ChooseTeamInterrupt } from "@/lib/events/schemas";

interface TeamPickerDialogProps {
  interrupt: ChooseTeamInterrupt;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pending: boolean;
  error: string | null;
  onChoose: (teamId: string) => void;
}

/** Asks which Linear team gets the plan. Esc closes it without answering; the prompt above the composer stays. */
export function TeamPickerDialog({ interrupt, open, onOpenChange, pending, error, onChoose }: TeamPickerDialogProps) {
  const [picked, setPicked] = useState<string>(interrupt.teams[0]?.id ?? "");
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent showCloseButton={false} className="sm:max-w-95">
        <DialogHeader>
          <DialogTitle>Choose a Linear team</DialogTitle>
          <DialogDescription>
            {interrupt.savedTeamId !== null
              ? "The team saved for this workspace is no longer in Linear. Pick another one."
              : "Metis remembers your choice for the next export."}
          </DialogDescription>
        </DialogHeader>
        <div role="radiogroup" aria-label="Linear team" className="grid max-h-64 gap-1 overflow-y-auto">
          {interrupt.teams.map((team) => (
            <label
              key={team.id}
              className={cn(
                "flex cursor-pointer items-center gap-2 border px-2.5 py-2 text-control has-focus-visible:bg-accent",
                picked === team.id && "border-foreground",
              )}
            >
              <input
                type="radio"
                name="linear-team"
                value={team.id}
                checked={picked === team.id}
                onChange={() => setPicked(team.id)}
                className="accent-foreground"
              />
              <span className="min-w-0 flex-1 truncate">{team.name}</span>
              <span className="font-mono text-meta text-muted-foreground">{team.key}</span>
            </label>
          ))}
        </div>
        {error ? (
          <p role="alert" className="text-meta text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button type="button" variant="outline" disabled={pending} onClick={() => onOpenChange(false)}>
            Later
          </Button>
          <Button type="button" disabled={pending || picked === ""} onClick={() => onChoose(picked)}>
            {pending ? "Sending…" : "Use this team"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
