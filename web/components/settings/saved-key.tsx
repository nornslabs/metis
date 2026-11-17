"use client";

import { Check, Loader } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useDeleteKey } from "@/lib/api/mutations/use-delete-key";
import type { ProviderKind } from "@/lib/api/mutations/use-save-key";
import { useTestKey } from "@/lib/api/mutations/use-test-key";
import type { components } from "@/lib/api/schema";
import { testFailureMessage } from "@/lib/settings/test-reason";

import { ConfirmDialog } from "./confirm-dialog";

type KeyView = components["schemas"]["ProviderKeyView"];

type SavedKeyProps = {
  kind: ProviderKind;
  view: KeyView;
  /** Owners may replace and remove; everyone may test. */
  canWrite: boolean;
  onReplace: () => void;
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** The saved key as the API shows it: masked, with its last test and Test / Replace / Remove. */
export function SavedKey({ kind, view, canWrite, onReplace }: SavedKeyProps) {
  const test = useTestKey();
  const remove = useDeleteKey();

  return (
    <div className="grid gap-1.5 border p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-note" data-testid={`saved-${kind}`}>
          Saved, {view.masked}
        </span>
        <div className="flex shrink-0 gap-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={test.isPending}
            onClick={() => test.mutate(kind)}
          >
            Test
          </Button>
          {canWrite ? (
            <>
              <Button type="button" variant="outline" size="sm" onClick={onReplace}>
                Replace
              </Button>
              <ConfirmDialog
                trigger={
                  <Button type="button" variant="destructive" size="sm" disabled={remove.isPending}>
                    Remove
                  </Button>
                }
                title={`Remove the ${kind === "llm" ? "LLM" : "Exa"} key?`}
                description="Runs that need it will stop until you add a new one."
                confirmLabel="Remove"
                onConfirm={() => remove.mutate(kind)}
              />
            </>
          ) : null}
        </div>
      </div>
      {view.base_url ? (
        <div className="truncate font-mono text-meta text-muted-foreground">
          {view.base_url} · {view.model}
        </div>
      ) : null}
      <TestStatus view={view} test={test} />
    </div>
  );
}

function TestStatus({ view, test }: { view: KeyView; test: ReturnType<typeof useTestKey> }) {
  if (test.isPending) {
    return (
      <p className="flex items-center gap-1 text-meta text-muted-foreground">
        <Loader size={12} className="animate-spin motion-reduce:animate-none" /> Testing…
      </p>
    );
  }
  if (test.isError) {
    return (
      <p role="alert" className="text-meta text-destructive">
        {testFailureMessage(test.error)}
      </p>
    );
  }
  if (test.isSuccess) {
    return (
      <p role="status" className="flex items-center gap-1 text-meta text-success">
        <Check size={12} /> Key works
      </p>
    );
  }
  if (view.last_tested_at) {
    const worked = view.last_test_ok === true;
    return (
      <p className={worked ? "text-meta text-muted-foreground" : "text-meta text-destructive"}>
        {worked ? "Worked" : "Failed"} · tested {formatTime(view.last_tested_at)}
      </p>
    );
  }
  return <p className="text-meta text-muted-foreground">Not tested yet.</p>;
}
