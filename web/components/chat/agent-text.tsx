import { SafeMarkdown } from "@/components/chat/safe-markdown";
import { cn } from "@/lib/utils";

interface AgentTextProps {
  text: string;
  streaming: boolean;
}

/** Streamed agent text as sanitized markdown, with a caret while it is still being written. */
export function AgentText({ text, streaming }: AgentTextProps) {
  if (text === "") return null;
  return (
    <div className={cn("flex flex-col gap-1.5 break-words [&_strong]:font-semibold", streaming && "streaming-caret")}>
      <SafeMarkdown text={text} />
    </div>
  );
}
