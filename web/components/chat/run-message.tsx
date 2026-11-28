import type { ReactNode } from "react";

import { AgentText } from "@/components/chat/agent-text";
import { RunErrorRow, RunNote } from "@/components/chat/run-notice";
import { RunNotices } from "@/components/chat/run-notices";
import { TypingDots } from "@/components/chat/typing-dots";
import { WorkSummary } from "@/components/chat/work-summary";
import { isActiveStatus, type RunState } from "@/lib/events/reducer";

interface RunMessageBodyProps {
  state: RunState;
  /** True when the live feed stopped before the run ended (closed by the server or the browser). */
  streamLost: boolean;
  /** Retry button for a failed run. */
  retry: ReactNode;
  /** Sources the Researcher used, when known: the work summary says "Researched 6 sources". */
  sourceCount: number | null;
  /** The output cards (score, research): one line each, never the report. */
  outputs?: ReactNode;
  /** The run's own text after its last question; defaults to all of it. */
  text?: string;
  /** The approval prompt and the user's earlier choices; always rendered, the caller decides what shows. */
  approval?: ReactNode;
}

/**
 * What the agent message shows for one run: the work summary (live steps run in the dock), the
 * output cards, text, and the run's outcome.
 */
export function RunMessageBody({ state, streamLost, retry, sourceCount, outputs, approval, text }: RunMessageBodyProps) {
  const working = isActiveStatus(state.status) && state.status !== "awaiting_user" && !streamLost;
  const bodyText = text ?? state.text;
  const streaming = working && state.status === "running";
  return (
    <>
      <WorkSummary steps={state.steps} sourceCount={sourceCount} working={working} />
      <RunNotices notices={state.notices} />
      {outputs}
      {bodyText ? <AgentText text={bodyText} streaming={streaming} /> : working ? <TypingDots /> : null}
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
