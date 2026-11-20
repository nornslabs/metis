"use client";

import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, describeError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/mutations/use-start-run";
import { useRefreshScore, type RefreshKind } from "@/lib/api/mutations/use-refresh-score";
import { useKeyGate } from "@/lib/api/queries/use-key-gate";
import { llmBlockMessage, llmNotReadyMessage } from "@/lib/keys/readiness";
import { queryKeys } from "@/lib/api/queries/keys";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";

const ALREADY_RUNNING = "run.already_running";
const NO_RESEARCH = "research.not_found";
const ALREADY_RUNNING_MESSAGE = "A run is already in progress for this idea.";
const NO_RESEARCH_MESSAGE = "Run research first: there is no finished research to re-check.";
const RUN_ACTIVE_NOTE = "Wait for the current run to finish.";

const ACTIONS: readonly { kind: RefreshKind; label: string; hint: string }[] = [
  { kind: "recheck-market", label: "Re-check market", hint: "Research again, then score" },
  { kind: "rescore", label: "Rescore", hint: "Score again on the research you have" },
];

function messageFor(caught: unknown): string {
  if (caught instanceof ApiError && caught.code === ALREADY_RUNNING) return ALREADY_RUNNING_MESSAGE;
  if (caught instanceof ApiError && caught.code === NO_RESEARCH) return NO_RESEARCH_MESSAGE;
  return llmNotReadyMessage(caught) ?? describeError(caught);
}

interface RefreshActionsProps {
  ideaId: string;
  /** True while a run of this idea is `queued`, `running` or `awaiting_user`. */
  runActive: boolean;
}

/** "Re-check market" and "Rescore": each starts a refresh run, and the page follows it. */
export function RefreshActions({ ideaId, runActive }: RefreshActionsProps) {
  const refresh = useRefreshScore();
  const gate = useKeyGate();
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  const [error, setError] = useState<string | null>(null);
  const blocked = gate.llmBlock ? llmBlockMessage(gate.llmBlock) : null;
  const disabled = runActive || blocked !== null || refresh.isPending;

  const start = (kind: RefreshKind) => {
    setError(null);
    refresh.mutate(
      { ideaId, kind, idempotencyKey: newIdempotencyKey() },
      {
        onError: (caught) => {
          setError(messageFor(caught));
          if (caught instanceof ApiError && caught.code === ALREADY_RUNNING) {
            void queryClient.invalidateQueries({ queryKey: queryKeys.idea(workspaceId, ideaId) });
          }
          if (llmNotReadyMessage(caught)) void queryClient.invalidateQueries({ queryKey: ["settings"] });
        },
      },
    );
  };

  const note = error ?? (blocked ? blocked : runActive ? RUN_ACTIVE_NOTE : null);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap gap-1.5">
        {ACTIONS.map(({ kind, label, hint }) => (
          <Button key={kind} type="button" variant="outline" size="sm" disabled={disabled} title={hint} onClick={() => start(kind)}>
            <RefreshCw size={13} aria-hidden="true" />
            {label}
          </Button>
        ))}
      </div>
      {note ? (
        <p role={error ? "alert" : "status"} className={error ? "text-meta text-destructive" : "text-meta text-muted-foreground"}>
          {note}
        </p>
      ) : null}
    </div>
  );
}
