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

/** The interview in the thread: each question as an agent message, each answer as the user's bubble. */
export function InterviewMessages({ messages }: { messages: readonly InterviewMessage[] }) {
  return (
    <>
      {messages.map((message) =>
        message.role === "agent" ? (
          <AgentMessage key={message.key}>
            <QuestionLine text={message.text} />
          </AgentMessage>
        ) : (
          <UserBubble key={message.key} text={message.text} picked={message.picked} />
        ),
      )}
    </>
  );
}
