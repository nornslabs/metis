"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { FormProvider, useForm } from "react-hook-form";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage, fieldErrors, isApiError } from "@/lib/api/errors";
import { useSaveKey } from "@/lib/api/mutations/use-save-key";
import { useUpdateSettings } from "@/lib/api/mutations/use-update-settings";
import { useCurrentWorkspace } from "@/lib/api/queries/use-current-workspace";
import { useSettings } from "@/lib/api/queries/use-settings";
import type { components } from "@/lib/api/schema";
import { keysFormSchema, type KeysFormValues } from "@/lib/schemas/settings-forms";

import { ExaKeyFields, LlmKeyFields, SarvamKeyFields } from "./key-fields";
import { RunLimitsFields } from "./run-limits-fields";
import { SettingsFooter } from "./settings-footer";
import { SettingsGroup } from "./settings-field";
import { SttProviderField } from "./stt-provider-field";

type SettingsResponse = components["schemas"]["SettingsResponse"];

const CONFLICT_STATUS = 409;
const CONFLICT_NOTICE = "Settings changed elsewhere; reloaded.";
const BUDGET_DECIMALS = 2;

function formValuesOf(settings: SettingsResponse): KeysFormValues {
  const s = settings.settings as SettingsResponse["settings"] & { stt_provider: string };
  const k = settings.keys as SettingsResponse["keys"] & { sarvam: components["schemas"]["ProviderKeyView"] | null | undefined };
  return {
    llm: { base_url: "", model: "", value: "" },
    exa: { value: "" },
    sarvam: { value: "" },
    run_budget_usd: s.run_budget_usd.toFixed(BUDGET_DECIMALS),
    max_steps: String(s.max_steps),
    stt_provider: s.stt_provider,
  };
}

/** The API keys tab: keys, run limits and the sheet's sticky Cancel / Save footer. */
export function KeysPanel({ onClose }: { onClose: () => void }) {
  const { data: settings } = useSettings();
  const { data: current } = useCurrentWorkspace();
  const [notice, setNotice] = useState<string | null>(null);

  if (!settings || !current) return <Skeleton className="m-4 h-60" />;

  // Keyed by version so a newer copy (our save, or a 409 reload) replaces what is on screen.
  return (
    <KeysForm
      key={settings.settings.version}
      settings={settings}
      canWrite={current.role === "owner"}
      notice={notice}
      onNotice={setNotice}
      onClose={onClose}
    />
  );
}

type KeysFormProps = {
  settings: SettingsResponse;
  canWrite: boolean;
  notice: string | null;
  onNotice: (notice: string | null) => void;
  onClose: () => void;
};

function KeysForm({ settings, canWrite, notice, onNotice, onClose }: KeysFormProps) {
  const [replacingLlm, setReplacingLlm] = useState(false);
  const [replacingExa, setReplacingExa] = useState(false);
  const [replacingSarvam, setReplacingSarvam] = useState(false);
  const saveKey = useSaveKey();
  const updateSettings = useUpdateSettings();
  const [formError, setFormError] = useState<string | null>(null);

  const form = useForm<KeysFormValues>({
    resolver: zodResolver(keysFormSchema),
    defaultValues: formValuesOf(settings),
    mode: "onChange",
  });
  const { handleSubmit, reset, setError } = form;
  // Read at render so react-hook-form re-renders on each of them (it only tracks what is read).
  const { isDirty, isValid, dirtyFields } = form.formState;

  const submit = handleSubmit(async (values) => {
    setFormError(null);
    onNotice(null);
    // The key being saved: the API names its fields `base_url`, the form nests them as `llm.base_url`.
    let savingKind: "llm" | "exa" | "sarvam" | null = null;
    try {
      if (values.llm.value.trim() !== "") {
        savingKind = "llm";
        await saveKey.mutateAsync({
          kind: "llm",
          body: {
            value: values.llm.value.trim(),
            base_url: values.llm.base_url.trim(),
            model: values.llm.model.trim(),
          },
        });
      }
      if (values.exa.value.trim() !== "") {
        savingKind = "exa";
        await saveKey.mutateAsync({ kind: "exa", body: { value: values.exa.value.trim() } });
      }
      if (values.sarvam.value.trim() !== "") {
        savingKind = "sarvam";
        await saveKey.mutateAsync({ kind: "sarvam" as unknown as components["schemas"]["ProviderKind"], body: { value: values.sarvam.value.trim() } });
      }
      savingKind = null;
      if (dirtyFields.run_budget_usd || dirtyFields.max_steps || dirtyFields.stt_provider) {
        await updateSettings.mutateAsync({
          version: settings.settings.version,
          run_budget_usd: Number(values.run_budget_usd).toFixed(BUDGET_DECIMALS),
          max_steps: Number(values.max_steps),
          stt_provider: values.stt_provider,
        } as never);
      }
      // Secrets are never kept: inputs empty, the saved key shows masked.
      reset({
        ...values,
        llm: { base_url: "", model: "", value: "" },
        exa: { value: "" },
        sarvam: { value: "" },
        run_budget_usd: Number(values.run_budget_usd).toFixed(BUDGET_DECIMALS),
        max_steps: String(settings.settings.max_steps),
        stt_provider: (settings.settings as unknown as { stt_provider: string }).stt_provider,
      });
      setReplacingLlm(false);
      setReplacingExa(false);
      setReplacingSarvam(false);
      toast.success("Settings saved");
    } catch (error) {
      if (!isApiError(error)) throw error;
      if (error.status === CONFLICT_STATUS) {
        onNotice(CONFLICT_NOTICE);
        return;
      }
      const fields = fieldErrors(error);
      for (const { name, error: fieldError } of fields) {
        const path = savingKind ? `${savingKind}.${name}` : name;
        setError(path as Parameters<typeof setError>[0], fieldError);
      }
      if (fields.length === 0) setFormError(errorMessage(error));
    }
  });

  const saving = saveKey.isPending || updateSettings.isPending;

  return (
    <FormProvider {...form}>
      <form onSubmit={submit} noValidate className="flex min-h-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto p-4">
          <div className="grid gap-4.5">
            {canWrite ? null : (
              <p className="border p-2.5 text-meta text-muted-foreground">
                Only workspace owners can change keys.
              </p>
            )}
            <SettingsGroup
              title="Language model"
              hint="Any OpenAI-compatible endpoint. Keys are encrypted and never shown again."
            >
              <LlmKeyFields
                view={settings.keys.llm}
                canWrite={canWrite}
                replacing={replacingLlm}
                onReplacingChange={setReplacingLlm}
              />
            </SettingsGroup>
            <SettingsGroup title="Research">
              <ExaKeyFields
                view={settings.keys.exa}
                canWrite={canWrite}
                replacing={replacingExa}
                onReplacingChange={setReplacingExa}
              />
            </SettingsGroup>
            <SettingsGroup title="Speech-to-text">
              <SarvamKeyFields
                view={(settings.keys as { sarvam: components["schemas"]["ProviderKeyView"] | null | undefined }).sarvam}
                canWrite={canWrite}
                replacing={replacingSarvam}
                onReplacingChange={setReplacingSarvam}
              />
            </SettingsGroup>
            <SettingsGroup title="STT provider">
              <SttProviderField
                value={(settings.settings as unknown as { stt_provider: string }).stt_provider}
                canWrite={canWrite}
                onChange={(value) => form.setValue("stt_provider", value)}
              />
            </SettingsGroup>
            <SettingsGroup title="Run limits">
              <RunLimitsFields readOnly={!canWrite} />
            </SettingsGroup>
            {notice ? (
              <p role="alert" className="text-meta text-warning">
                {notice}
              </p>
            ) : null}
            {formError ? (
              <p role="alert" className="text-meta text-destructive">
                {formError}
              </p>
            ) : null}
          </div>
        </div>
        {canWrite ? (
          <SettingsFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!isDirty || !isValid || saving}>
              Save changes
            </Button>
          </SettingsFooter>
        ) : null}
      </form>
    </FormProvider>
  );
}
