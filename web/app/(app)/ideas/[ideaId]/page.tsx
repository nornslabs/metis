import { Suspense } from "react";

import { ConversationSkeleton, IdeaConversation } from "@/components/chat/idea-conversation";

type IdeaPageProps = PageProps<"/ideas/[ideaId]">;

// Route params are request data: read them behind a boundary so the shell still prerenders.
async function IdeaFromParams({ params }: Pick<IdeaPageProps, "params">) {
  const { ideaId } = await params;
  return <IdeaConversation ideaId={ideaId} />;
}

export default function IdeaPage({ params }: IdeaPageProps) {
  return (
    <Suspense fallback={<ConversationSkeleton />}>
      <IdeaFromParams params={params} />
    </Suspense>
  );
}
