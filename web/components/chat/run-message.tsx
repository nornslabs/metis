import type { ReactNode } from "react";

import { AgentText } from "@/components/chat/agent-text";
import { InterruptPlaceholder, RunErrorRow, RunNote } from "@/components/chat/run-notice";
import { Shimmer } from "@/components/chat/shimmer";
import { StepList } from "@/components/chat/step-list";
import { nodeLabel } from "@/lib/events/labels";
import { isActiveStatus, type RunState } from "@/lib/events/reducer";

/** The shimmer label: the step running now, else what the run is waiting for. */
function currentLabel(state: RunState): string {
  const running = state.steps.findLast((step) => !step.done);
  if (running) return `${nodeLabel(running.node)}…`;
  return state.status === "queued" ? "Starting…" : "Thinking…";
}

interface RunMessageBodyProps {
  state: RunState;
  /** True when the live feed stopped before the run ended (closed by the server or the browser). */
  streamLost: boolean;
  /** Retry button for a failed run. */
  retry: ReactNode;
}

/** What the agent message shows for one run: steps, text, and the run's outcome. */
export function RunMessageBody({ state, streamLost, retry }: RunMessageBodyProps) {
  const working = isActiveStatus(state.status) && state.status !== "awaiting_user" && !streamLost;
  return (
    <>
      <StepList steps={state.steps} live={working} />
      <AgentText text={state.text} streaming={working && state.status === "running"} />
      {working && state.text === "" ? <Shimmer>{currentLabel(state)}</Shimmer> : null}
      {streamLost ? (
        <RunNote>Live updates stopped. Reload the page to see the latest progress.</RunNote>
      ) : null}
      {state.status === "awaiting_user" && state.interrupt ? (
        <InterruptPlaceholder interrupt={state.interrupt} />
      ) : null}
      {state.status === "failed" && state.error ? <RunErrorRow error={state.error} action={retry} /> : null}
      {state.status === "cancelled" ? <RunNote>Run stopped.</RunNote> : null}
      {state.status === "succeeded" ? <RunNote>Run finished.</RunNote> : null}
    </>
  );
}
