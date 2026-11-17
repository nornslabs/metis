import type { ReactNode } from "react";

import { Label } from "@/components/ui/label";

type SettingsGroupProps = { title: string; hint?: string; children: ReactNode };

/** A titled block of fields: 11px uppercase label, optional hint, 10px gap. */
export function SettingsGroup({ title, hint, children }: SettingsGroupProps) {
  return (
    <section className="grid gap-2.5">
      <h3 className="text-meta font-medium tracking-label text-muted-foreground uppercase">
        {title}
      </h3>
      {hint ? <p className="-mt-1.5 text-note text-muted-foreground">{hint}</p> : null}
      {children}
    </section>
  );
}

type FieldProps = {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
};

/** Label, control, then the hint or the field's error (announced to screen readers). */
export function Field({ id, label, hint, error, children }: FieldProps) {
  return (
    <div className="grid gap-1">
      <Label htmlFor={id} className="text-control">
        {label}
      </Label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-meta text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p className="text-meta text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
