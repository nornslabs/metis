"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { Composer } from "@/components/chat/composer";
import { KEY_GATE_NOTICE_ID, KeyGateNotice } from "@/components/chat/key-gate-notice";
import { Button } from "@/components/ui/button";
import { ApiError, describeError, fieldErrors } from "@/lib/api/errors";
import { useCreateIdea } from "@/lib/api/mutations/use-create-idea";
import { newIdempotencyKey, useStartRun } from "@/lib/api/mutations/use-start-run";
import { useKeyGate } from "@/lib/api/queries/use-key-gate";
import { llmNotReadyMessage } from "@/lib/keys/readiness";
import { ideaFormSchema, toNewIdea, type IdeaFormValues } from "@/lib/schemas/idea-form";

const SUGGESTIONS = [
  "A habit tracker for remote teams",
  "AI tutor for spoken Spanish",
  "Marketplace for used lab equipment",
] as const;

/** Creates the idea, then starts its first run; the idea page offers Start if the run did not start. */
function useSubmitIdea() {
  const router = useRouter();
  const createIdea = useCreateIdea();
  const startRun = useStartRun();
  const queryClient = useQueryClient();
  const [error, setError] = useState<unknown>(null);

  const submit = async (values: IdeaFormValues) => {
    setError(null);
    let ideaId: string;
    try {
      ideaId = (await createIdea.mutateAsync(toNewIdea(values))).id;
    } catch (caught) {
      setError(caught);
      return;
    }
    try {
      await startRun.mutateAsync({ ideaId, idempotencyKey: newIdempotencyKey() });
    } catch (caught) {
      // The idea exists, so go to it anyway (its page offers Start); the page changes under the
      // reader, so the reason goes in a toast.
      const notReady = llmNotReadyMessage(caught);
      if (notReady) void queryClient.invalidateQueries({ queryKey: ["settings"] });
      toast.error("Your idea was saved, but its run did not start.", {
        description: notReady ?? describeError(caught),
        ...(notReady && { action: { label: "Open API keys", onClick: () => router.replace(`/ideas/${ideaId}?settings=keys`) } }),
      });
    }
    router.push(`/ideas/${ideaId}`);
  };

  return { submit, pending: createIdea.isPending || startRun.isPending, error };
}

/** The empty chat on `/`: title, suggestions and the composer that submits a new idea. */
export function EmptyChat() {
  const { submit, pending, error } = useSubmitIdea();
  const gate = useKeyGate();
  const blocked = gate.llmBlock !== null;
  const form = useForm<IdeaFormValues>({
    resolver: zodResolver(ideaFormSchema),
    defaultValues: { text: "" },
  });
  const text = useWatch({ control: form.control, name: "text" });
  const fieldError = form.formState.errors.text?.message;
  const serverFieldError =
    error instanceof ApiError ? fieldErrors(error).find(({ name }) => name === "raw_text" || name === "title") : undefined;
  const composerError = fieldError ?? serverFieldError?.error.message ?? (error ? describeError(error) : null);

  return (
    <>
      <section className="flex flex-1 flex-col items-center justify-center gap-1.5 px-5 py-8 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">What are you building?</h1>
        <p className="max-w-lead text-body text-muted-foreground">
          Describe your idea in a sentence or two. Metis will ask a few questions, research the market and
          score it.
        </p>
      </section>
      <div className="mx-auto flex w-(--col) shrink-0 flex-wrap justify-center gap-1.5 px-5 pb-3 max-guides:px-4">
        {SUGGESTIONS.map((suggestion) => (
          <Button
            key={suggestion}
            type="button"
            variant="outline"
            className="h-6 px-2 text-xs"
            onClick={() => form.setValue("text", suggestion, { shouldValidate: form.formState.isSubmitted })}
          >
            {suggestion}
          </Button>
        ))}
      </div>
      <Composer
        label="Your idea"
        textarea={{
          ...form.register("text"),
          placeholder: "Describe your idea…",
          readOnly: pending || blocked,
          "aria-describedby": blocked ? KEY_GATE_NOTICE_ID : undefined,
        }}
        action="send"
        canSend={!pending && !blocked && text.trim() !== ""}
        above={<KeyGateNotice gate={gate} includeExa />}
        onSubmit={form.handleSubmit(submit)}
        error={composerError}
      />
    </>
  );
}
