"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { AgentMessage } from "@/components/chat/agent-message";
import { Thread } from "@/components/chat/thread";
import { UserBubble } from "@/components/chat/user-bubble";
import { Badge } from "@/components/ui/badge";
import type { components } from "@/lib/api/schema";
import { stageLabel } from "@/lib/events/labels";

type Idea = components["schemas"]["Idea"];

// Follow new content only when the reader is this close to the bottom (after it rendered).
const STICK_THRESHOLD_PX = 480;

/** Keeps the newest content in view while the reader is already at the bottom. */
function useStickToBottom(dependency: unknown) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const end = endRef.current;
    const scroller = end?.closest("[data-scroll]");
    if (!end || !scroller) return;
    const distance = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    if (distance < STICK_THRESHOLD_PX) end.scrollIntoView({ block: "end" });
  }, [dependency]);
  return endRef;
}

interface ConversationLayoutProps {
  idea: Idea;
  /** The interview so far (questions and answers), between the idea and the run's message. */
  interview?: ReactNode;
  /** The agent message's content. */
  body: ReactNode;
  /** The composer band at the bottom. */
  composer: ReactNode;
  /** Changes when the content grows; a new value follows the newest content (compared by value). */
  scrollKey?: string;
}

/** The idea page: the idea, the interview, Metis's message for the run, and the composer. */
export function ConversationLayout({ idea, interview, body, composer, scrollKey }: ConversationLayoutProps) {
  const endRef = useStickToBottom(scrollKey);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div data-scroll className="min-h-0 flex-1 overflow-y-auto">
        <Thread>
          <UserBubble text={idea.raw_text} />
          {interview}
          <AgentMessage
            aside={
              <Badge variant="outline" className="h-badge px-1.5 text-meta font-normal" aria-label={`Stage: ${stageLabel(idea.stage)}`}>
                {stageLabel(idea.stage)}
              </Badge>
            }
          >
            {body}
          </AgentMessage>
          <div ref={endRef} />
        </Thread>
      </div>
      {composer}
    </div>
  );
}
