import { AgentMessage } from "@/components/chat/agent-message";
import { AgentText } from "@/components/chat/agent-text";
import { UserBubble } from "@/components/chat/user-bubble";
import type { InterviewMessage } from "@/lib/interview/thread";

/** A question line: a small `Q` tag, then the question in medium weight (ui-context.md, AgentMessage). */
function QuestionLine({ text }: { text: string }) {
  return (
    <div className="flex items-baseline gap-1.5 font-medium">
      <span aria-hidden="true" className="border px-1 font-mono text-micro font-medium text-muted-foreground">
        Q
      </span>
      <AgentText text={text} streaming={false} />
    </div>
  );
}

interface InterviewMessagesProps {
  messages: readonly InterviewMessage[];
  /** What Metis wrote before each question (`leads[i]` goes above question i), in order. */
  leads?: readonly string[];
}

/**
 * The interview in the thread: each question as an agent message, each answer as the user's
 * bubble, and the text Metis wrote after an answer just above the question that followed it.
 */
export function InterviewMessages({ messages, leads = [] }: InterviewMessagesProps) {
  // The question each message belongs to: an agent message starts a new one.
  const questionOf = messages.map((_, index) => messages.slice(0, index + 1).filter((m) => m.role === "agent").length - 1);
  return (
    <>
      {messages.map((message, index) => {
        const lead = message.role === "agent" ? (leads[questionOf[index] ?? 0] ?? "") : "";
        return message.role === "agent" ? (
          <AgentMessage key={message.key}>
            <AgentText text={lead} streaming={false} />
            <QuestionLine text={message.text} />
          </AgentMessage>
        ) : (
          <UserBubble key={message.key} text={message.text} picked={message.picked} />
        );
      })}
    </>
  );
}
