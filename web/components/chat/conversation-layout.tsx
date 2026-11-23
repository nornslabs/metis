"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { AgentMessage } from "@/components/chat/agent-message";
import { Thread } from "@/components/chat/thread";
import type { OwlState } from "@/components/brand/owl-mark";
import { UserBubble } from "@/components/chat/user-bubble";
import { Badge } from "@/components/ui/badge";
import type { components } from "@/lib/api/schema";
import { distanceFromBottom, shouldFollow } from "@/lib/chat/scroll";
import { stageLabel } from "@/lib/events/labels";

type Idea = components["schemas"]["Idea"];

/** Keeps the newest content in view while the reader is near the bottom, or just sent a message. */
function useStickToBottom(dependency: unknown, sentCount: number) {
  const endRef = useRef<HTMLDivElement>(null);
  const lastSent = useRef(sentCount);
  useEffect(() => {
    const end = endRef.current;
    const scroller = end?.closest("[data-scroll]");
    if (!end || !scroller) return;
    const justSent = sentCount !== lastSent.current;
    lastSent.current = sentCount;
    const distance = distanceFromBottom(scroller.scrollHeight, scroller.scrollTop, scroller.clientHeight);
    if (shouldFollow(distance, justSent)) end.scrollIntoView({ block: "end" });
  }, [dependency, sentCount]);
  return endRef;
}

interface ConversationLayoutProps {
  idea: Idea;
  /** The interview so far (questions and answers), between the idea and the run's message. */
  interview?: ReactNode;
  /** The agent message's content. */
  body: ReactNode;
  /** The dock at the bottom: the composer, the answer options or the working bar. */
  composer: ReactNode;
  /** The latest agent message's owl: `working` while busy, `waiting` while the dock asks. */
  owl?: OwlState;
  /** Answers and messages the user sent; a change scrolls to the bottom even if the reader had scrolled up. */
  sentCount?: number;
  /** Changes when the content grows; a new value follows the newest content (compared by value). */
  scrollKey?: string;
}

/** The idea page: the idea, the interview, Metis's message for the run, and the composer. */
export function ConversationLayout({ idea, interview, body, composer, scrollKey, owl, sentCount = 0 }: ConversationLayoutProps) {
  const endRef = useStickToBottom(scrollKey, sentCount);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div data-scroll className="min-h-0 flex-1 overflow-y-auto">
        <Thread>
          <UserBubble text={idea.raw_text} />
          {interview}
          <AgentMessage
            owl={owl}
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
