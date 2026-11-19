import { AgentMessage } from "@/components/chat/agent-message";
import { AgentText } from "@/components/chat/agent-text";
import { UserBubble } from "@/components/chat/user-bubble";
import type { InterviewMessage } from "@/lib/interview/thread";

/** The interview in the thread: each question as an agent message, each answer as the user's bubble. */
export function InterviewMessages({ messages }: { messages: readonly InterviewMessage[] }) {
  return (
    <>
      {messages.map((message) =>
        message.role === "agent" ? (
          <AgentMessage key={message.key}>
            <AgentText text={message.text} streaming={false} />
          </AgentMessage>
        ) : (
          <UserBubble key={message.key} text={message.text} />
        ),
      )}
    </>
  );
}
