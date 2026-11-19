import type { ReactNode } from "react";

import { AgentText } from "@/components/chat/agent-text";
import { RunErrorRow, RunNote } from "@/components/chat/run-notice";
import { RunNotices } from "@/components/chat/run-notices";
import { Shimmer } from "@/components/chat/shimmer";
import { StepList } from "@/components/chat/step-list";
import { runActivity } from "@/lib/events/activity";
import { isActiveStatus, type RunState } from "@/lib/events/reducer";

interface RunMessageBodyProps {
  state: RunState;
  /** True when the live feed stopped before the run ended (closed by the server or the browser). */
  streamLost: boolean;
  /** Retry button for a failed run. */
  retry: ReactNode;
  /** Sources chips and the research block, shown under the steps. */
  research?: ReactNode;
  /** The approval prompt and the user's earlier choices; always rendered, the caller decides what shows. */
  approval?: ReactNode;
}

/** What the agent message shows for one run: steps, research, text, and the run's outcome. */
export function RunMessageBody({ state, streamLost, retry, research, approval }: RunMessageBodyProps) {
  const working = isActiveStatus(state.status) && state.status !== "awaiting_user" && !streamLost;
  return (
    <>
      <StepList steps={state.steps} live={working} />
      <RunNotices notices={state.notices} />
      {research}
      <AgentText text={state.text} streaming={working && state.status === "running"} />
      {working && state.text === "" ? <Shimmer>{runActivity(state)}</Shimmer> : null}
      {streamLost ? (
        <RunNote>Live updates stopped. Reload the page to see the latest progress.</RunNote>
      ) : null}
      {approval}
      {state.status === "failed" && state.error ? <RunErrorRow error={state.error} action={retry} /> : null}
      {state.status === "cancelled" ? <RunNote>Run stopped.</RunNote> : null}
      {state.status === "succeeded" ? <RunNote>Run finished.</RunNote> : null}
    </>
  );
}
