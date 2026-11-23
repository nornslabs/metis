"use client";

import { AgentMessage } from "@/components/chat/agent-message";
import { OutputCards } from "@/components/chat/output-cards";
import { RunMessageBody } from "@/components/chat/run-message";
import { InterviewMessages } from "@/components/chat/interview-messages";
import { UserBubble } from "@/components/chat/user-bubble";
import type { components } from "@/lib/api/schema";
import { outputStarts } from "@/lib/events/output-starts";
import { isActiveStatus } from "@/lib/events/reducer";
import { useRunEvents } from "@/lib/events/use-run-events";
import { countQuestions, splitSegments } from "@/lib/interview/segments";
import type { InterviewMessage } from "@/lib/interview/thread";

type Idea = components["schemas"]["Idea"];
type RunView = components["schemas"]["RunView"];

interface PastRunTurnProps {
  idea: Idea;
  run: RunView;
  /** The questions and answers of this run, shown between its prompt and its message. */
  interview: readonly InterviewMessage[];
  /** True for the one turn that shows the output cards (the run that did the work). */
  showOutputs: boolean;
}

/**
 * An earlier run, read-only: its prompt (none for the first run, whose prompt is the idea), then
 * Metis's message for it. The stream replays from the start, so a finished run rebuilds its steps
 * and text. No composer, approvals or retry: only the latest run is live.
 */
export function PastRunTurn({ idea, run, interview, showOutputs }: PastRunTurnProps) {
  // Read-only: a replay ending refreshes nothing; the live run owns the refetches.
  const { state, stream } = useRunEvents(run.id, run);
  const streamLost = stream === "failed";
  const { leads, tail } = splitSegments(state.segments, countQuestions(interview));
  return (
    <>
      {run.user_prompt ? <UserBubble text={run.user_prompt} /> : null}
      <InterviewMessages messages={interview} leads={leads} />
      <AgentMessage>
        <RunMessageBody
          state={state}
          text={tail}
          streamLost={streamLost}
          sourceCount={null}
          retry={null}
          outputs={
            showOutputs ? (
              <OutputCards
                ideaId={idea.id}
                ideaTitle={idea.title}
                runActive={isActiveStatus(state.status)}
                {...outputStarts(state.steps, idea.stage)}
                runId={run.id}
                runStatus={state.status}
                phaseReview={null}
              />
            ) : null
          }
        />
      </AgentMessage>
    </>
  );
}
