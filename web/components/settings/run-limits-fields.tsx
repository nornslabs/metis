"use client";

import { useFormContext } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { MAX_BUDGET_USD, MAX_STEPS, type KeysFormValues } from "@/lib/schemas/settings-forms";

import { Field } from "./settings-field";

/** Per-run spend cap (USD) and step cap; saved with the sheet's Save button. */
export function RunLimitsFields({ readOnly }: { readOnly: boolean }) {
  const { register, formState } = useFormContext<KeysFormValues>();
  const { errors } = formState;

  return (
    <div className="grid gap-2.5">
      <Field
        id="run-budget"
        label="Budget per run (USD)"
        hint={`Up to ${MAX_BUDGET_USD}. A run stops when it reaches this.`}
        error={errors.run_budget_usd?.message}
      >
        <Input
          id="run-budget"
          inputMode="decimal"
          autoComplete="off"
          readOnly={readOnly}
          aria-invalid={errors.run_budget_usd ? true : undefined}
          className="h-control text-control"
          {...register("run_budget_usd")}
        />
      </Field>
      <Field
        id="run-steps"
        label="Max steps per run"
        hint={`Whole number up to ${MAX_STEPS}.`}
        error={errors.max_steps?.message}
      >
        <Input
          id="run-steps"
          inputMode="numeric"
          autoComplete="off"
          readOnly={readOnly}
          aria-invalid={errors.max_steps ? true : undefined}
          className="h-control text-control"
          {...register("max_steps")}
        />
      </Field>
    </div>
  );
}
