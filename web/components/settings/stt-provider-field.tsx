"use client";

import { useState } from "react";
import { useFormContext } from "react-hook-form";

import type { KeysFormValues } from "@/lib/schemas/settings-forms";

type SttProviderFieldProps = {
  value: string;
  canWrite: boolean;
  onChange: (value: string) => void;
};

const STT_PROVIDERS = [
  { value: "web-speech", label: "Web Speech API (free)" },
  { value: "sarvam", label: "Sarvam (requires API key)" },
  { value: "mock", label: "Mock (tests only)" },
] as const;

/** Dropdown to select the speech-to-text provider. */
export function SttProviderField({ value, canWrite, onChange }: SttProviderFieldProps) {
  const { setValue, watch } = useFormContext<KeysFormValues>();
  const [mounted, setMounted] = useState(false);

  // Use a ref to track if we've mounted, and set state in a timeout to avoid synchronous setState in effect
  if (typeof window !== "undefined" && !mounted) {
    setMounted(true);
  }

  const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const val = event.target.value;
    setValue("stt_provider", val);
    onChange(val);
  };

  // Use watched value only after hydration to avoid mismatch
  const currentValue = mounted ? watch("stt_provider", value) : value;

  return (
    <div className="grid gap-2.5">
      <label className="text-xs text-muted-foreground">STT provider</label>
      <select
        value={currentValue}
        disabled={!canWrite}
        onChange={handleChange}
        className="w-full h-control rounded-md border border-input bg-background px-2 py-1 text-note disabled:opacity-50"
        suppressHydrationWarning
      >
        {STT_PROVIDERS.map((provider) => (
          <option key={provider.value} value={provider.value}>
            {provider.label}
          </option>
        ))}
      </select>
      {!canWrite && (
        <p className="text-meta text-muted-foreground text-xs">
          Only workspace owners can change the STT provider.
        </p>
      )}
    </div>
  );
}
