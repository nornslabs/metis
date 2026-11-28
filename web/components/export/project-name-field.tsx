import { useId } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/cn";
import { MAX_PROJECT_NAME_CHARS, projectNameError } from "@/lib/schemas/export";

interface ProjectNameFieldProps {
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}

/** The Linear project name: editable, with the trimmed character count and the 80-character rule. */
export function ProjectNameField({ value, onChange, disabled }: ProjectNameFieldProps) {
  const id = useId();
  const error = projectNameError(value);
  const length = value.trim().length;
  return (
    <div className="grid gap-1">
      <div className="flex items-baseline justify-between gap-3">
        <Label htmlFor={id} className="text-control">
          Project name
        </Label>
        <span
          id={`${id}-count`}
          className={cn(
            "font-mono text-meta",
            length > MAX_PROJECT_NAME_CHARS ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {length} / {MAX_PROJECT_NAME_CHARS}
        </span>
      </div>
      <Input
        id={id}
        value={value}
        disabled={disabled}
        aria-invalid={error !== null}
        aria-describedby={`${id}-count ${id}-error`}
        autoComplete="off"
        onChange={(event) => onChange(event.target.value)}
        className="text-control"
      />
      <p id={`${id}-error`} role={error ? "alert" : undefined} className="min-h-4 text-meta text-destructive">
        {error}
      </p>
    </div>
  );
}
