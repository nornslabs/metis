"use client";

import { useFormContext } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { components } from "@/lib/api/schema";
import type { KeysFormValues } from "@/lib/schemas/settings-forms";

import { Field } from "./settings-field";
import { SavedKey } from "./saved-key";

type KeyView = components["schemas"]["ProviderKeyView"] | null | undefined;

type KeyFieldsProps = {
  view: KeyView;
  canWrite: boolean;
  replacing: boolean;
  onReplacingChange: (replacing: boolean) => void;
};

const MONO_INPUT = "h-control font-mono text-note";

function NotSet() {
  return (
    <p className="border p-2.5 text-meta text-muted-foreground">
      No key saved. Only workspace owners can add one.
    </p>
  );
}

/** Base URL, model and key of the OpenAI-compatible endpoint; the key is write-only. */
export function LlmKeyFields({ view, canWrite, replacing, onReplacingChange }: KeyFieldsProps) {
  const { register, setValue, resetField, trigger, formState } = useFormContext<KeysFormValues>();
  const errors = formState.errors.llm;

  if (view && !replacing) {
    return (
      <SavedKey
        kind="llm"
        view={view}
        canWrite={canWrite}
        onReplace={() => {
          setValue("llm.base_url", view.base_url ?? "");
          setValue("llm.model", view.model ?? "");
          onReplacingChange(true);
        }}
      />
    );
  }
  if (!canWrite) return <NotSet />;

  return (
    <div className="grid gap-2.5">
      <Field id="llm-base-url" label="Base URL" error={errors?.base_url?.message}>
        <Input
          id="llm-base-url"
          inputMode="url"
          autoComplete="off"
          placeholder="https://api.openai.com/v1"
          aria-invalid={errors?.base_url ? true : undefined}
          aria-describedby={errors?.base_url ? "llm-base-url-error" : undefined}
          className={MONO_INPUT}
          {...register("llm.base_url")}
        />
      </Field>
      <Field id="llm-model" label="Model" error={errors?.model?.message}>
        <Input
          id="llm-model"
          autoComplete="off"
          placeholder="gpt-4.1"
          aria-invalid={errors?.model ? true : undefined}
          aria-describedby={errors?.model ? "llm-model-error" : undefined}
          className={MONO_INPUT}
          {...register("llm.model")}
        />
      </Field>
      <Field
        id="llm-key"
        label="API key"
        hint="Encrypted on save and never shown again."
        error={errors?.value?.message}
      >
        <Input
          id="llm-key"
          type="password"
          autoComplete="off"
          placeholder="Paste your key"
          aria-invalid={errors?.value ? true : undefined}
          className={MONO_INPUT}
          // Entering a key makes the base URL and model required: say so as soon as it happens.
          {...register("llm.value", { onChange: () => void trigger(["llm.base_url", "llm.model"]) })}
        />
      </Field>
      {view ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="justify-self-start"
          onClick={() => {
            resetField("llm");
            onReplacingChange(false);
          }}
        >
          Keep the saved key
        </Button>
      ) : null}
    </div>
  );
}

/** The Exa search key; write-only like the LLM key. */
export function ExaKeyFields({ view, canWrite, replacing, onReplacingChange }: KeyFieldsProps) {
  const { register, resetField, formState } = useFormContext<KeysFormValues>();
  const error = formState.errors.exa?.value?.message;

  if (view && !replacing) {
    return (
      <SavedKey kind="exa" view={view} canWrite={canWrite} onReplace={() => onReplacingChange(true)} />
    );
  }
  if (!canWrite) return <NotSet />;

  return (
    <div className="grid gap-2.5">
      <Field
        id="exa-key"
        label="Exa API key"
        hint="Encrypted on save and never shown again."
        error={error}
      >
        <Input
          id="exa-key"
          type="password"
          autoComplete="off"
          placeholder="Paste your Exa key"
          aria-invalid={error ? true : undefined}
          className={MONO_INPUT}
          {...register("exa.value")}
        />
      </Field>
      {view ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="justify-self-start"
          onClick={() => {
            resetField("exa");
            onReplacingChange(false);
          }}
        >
          Keep the saved key
        </Button>
      ) : null}
    </div>
  );
}

/** The Sarvam speech-to-text API key; write-only like the Exa key. */
export function SarvamKeyFields({ view, canWrite, replacing, onReplacingChange }: KeyFieldsProps) {
  const { register, resetField, formState } = useFormContext<KeysFormValues>();
  const error = formState.errors.sarvam?.value?.message;

  if (view && !replacing) {
    return (
      <SavedKey kind={"sarvam" as unknown as components["schemas"]["ProviderKind"]} view={view} canWrite={canWrite} onReplace={() => onReplacingChange(true)} />
    );
  }
  if (!canWrite) return <NotSet />;

  return (
    <div className="grid gap-2.5">
      <Field
        id="sarvam-key"
        label="Sarvam API key"
        hint="Encrypted on save and never shown again."
        error={error}
      >
        <Input
          id="sarvam-key"
          type="password"
          autoComplete="off"
          placeholder="Paste your Sarvam key"
          aria-invalid={error ? true : undefined}
          className={MONO_INPUT}
          {...register("sarvam.value")}
        />
      </Field>
      {view ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="justify-self-start"
          onClick={() => {
            resetField("sarvam");
            onReplacingChange(false);
          }}
        >
          Keep the saved key
        </Button>
      ) : null}
    </div>
  );
}
