import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

// Agent text is untrusted: raw HTML is dropped (`skipHtml`), links open safely, images are not
// loaded (they could track the reader).
const COMPONENTS: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="underline underline-offset-2">
      {children}
    </a>
  ),
  img: ({ alt }) => <span>{alt ?? ""}</span>,
  ul: ({ children }) => <ul className="list-disc pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5">{children}</ol>,
  code: ({ children }) => <code className="bg-muted px-1 font-mono text-note">{children}</code>,
  pre: ({ children }) => <pre className="overflow-x-auto bg-muted p-2 font-mono text-note">{children}</pre>,
};

interface AgentTextProps {
  text: string;
  streaming: boolean;
}

/** Streamed agent text as sanitized markdown, with a caret while it is still being written. */
export function AgentText({ text, streaming }: AgentTextProps) {
  if (text === "") return null;
  return (
    <div className={cn("flex flex-col gap-1.5 break-words [&_strong]:font-semibold", streaming && "streaming-caret")}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={COMPONENTS}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
