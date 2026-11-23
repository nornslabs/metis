"use client";

import { Check } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { keyChoice, keyHint, questionHeading, recommendedIds, toggleId, OTHER_KEY } from "@/lib/chat/choice";
import type { QuestionInterrupt, QuestionOption } from "@/lib/events/schemas";
import { hasOpenOverlay, isTypingTarget } from "@/lib/workspace/dom-guards";
import { cn } from "@/lib/utils";

interface ChoicePickerProps {
  question: QuestionInterrupt & { options: readonly QuestionOption[] };
  /** True while an answer is on its way: nothing can be picked. */
  disabled: boolean;
  onPick: (optionIds: readonly string[]) => void;
  /** "Something else, let me type it": the composer takes the dock. */
  onOther: () => void;
  /** Ends the run that waits for this answer. */
  onStop: () => void;
  stopping: boolean;
}

const INTERACTIVE = "button, a, input, textarea, select";
/** Rows carry this mark: Enter on a focused row confirms the pick (a mouse click leaves focus there). */
const OPTION_ROW = "[data-option]";

function KeyBox({ label, checked, multi }: { label: string; checked: boolean; multi: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-5 place-items-center border font-mono text-eyebrow text-muted-foreground",
        multi && checked && "border-foreground bg-foreground text-background",
      )}
    >
      {multi && checked ? <Check size={12} strokeWidth={3} /> : label}
    </span>
  );
}

function OptionRow({
  option,
  position,
  multi,
  checked,
  disabled,
  onSelect,
}: {
  option: QuestionOption;
  position: number;
  multi: boolean;
  checked: boolean;
  disabled: boolean;
  onSelect: (option: QuestionOption) => void;
}) {
  return (
    <button
      type="button"
      role={multi ? "checkbox" : undefined}
      aria-checked={multi ? checked : undefined}
      aria-keyshortcuts={String(position)}
      data-option=""
      disabled={disabled}
      onClick={() => onSelect(option)}
      className={cn(
        "grid w-full grid-cols-[auto_1fr_auto] items-center gap-2.5 border-b py-1.75 pr-3 pl-5 text-left last:border-b-0 max-guides:pl-4",
        "transition-colors hover:bg-accent relative before:absolute before:inset-y-0 before:left-0 before:w-0 before:bg-foreground focus-visible:before:w-0.5 focus-visible:bg-accent focus-visible:outline-none",
        "disabled:cursor-not-allowed disabled:opacity-50",
        multi && checked && "bg-accent/70",
      )}
    >
      <KeyBox label={String(position)} checked={checked} multi={multi} />
      <span className="min-w-0">
        <span className="block text-body leading-snug font-medium">{option.label}</span>
        {option.detail ? <span className="block text-note leading-snug text-muted-foreground">{option.detail}</span> : null}
      </span>
      {option.recommended ? (
        <span className="border border-foreground px-1.25 text-micro leading-4 font-medium tracking-label uppercase">
          Best fit
        </span>
      ) : null}
    </button>
  );
}

/**
 * The dock while Metis asks and offers answers: a numbered row per option, a "Best fit" tag, and
 * "Something else" last. Everything works from the keyboard: 1–9 pick (or toggle), 0 types, and
 * Enter confirms a multi-choice (ui-context.md, ChoicePicker).
 */
export function ChoicePicker({ question, disabled, onPick, onOther, onStop, stopping }: ChoicePickerProps) {
  const { options, multi = false, allowFreeText = true } = question;
  const headingId = useId();
  const [checked, setChecked] = useState<readonly string[]>(() => (multi ? recommendedIds(options) : []));
  const latest = useRef({ checked, disabled, multi, options, allowFreeText, onPick, onOther });
  // The key handler is bound once; it reads the newest props and picks from here.
  useEffect(() => {
    latest.current = { checked, disabled, multi, options, allowFreeText, onPick, onOther };
  });

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const now = latest.current;
      if (event.defaultPrevented || now.disabled || event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target) || hasOpenOverlay()) return;
      if (event.key === "Enter") {
        const target = event.target instanceof Element ? event.target : null;
        const onOwnControl = target?.closest(INTERACTIVE) && !target.closest(OPTION_ROW);
        if (!now.multi || now.checked.length === 0 || onOwnControl) return;
        event.preventDefault();
        now.onPick(now.checked);
        return;
      }
      const choice = keyChoice(event.key, now.options, now.allowFreeText);
      if (choice === null) return;
      event.preventDefault();
      if (choice.kind === "other") now.onOther();
      else if (now.multi) setChecked((current) => toggleId(current, choice.option.id));
      else now.onPick([choice.option.id]);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const select = (option: QuestionOption) => {
    if (multi) setChecked((current) => toggleId(current, option.id));
    else onPick([option.id]);
  };

  return (
    <div role="group" aria-labelledby={headingId} className="chat-col border-x bg-card">
      <div className="flex items-center justify-between gap-2 border-b py-1.5 pr-3 pl-5 max-guides:pl-4">
        <span id={headingId} className="text-meta font-medium tracking-label text-muted-foreground uppercase">
          {questionHeading(question.index, question.total)}
        </span>
        <span className="flex items-center gap-2">
          <kbd className="font-mono text-eyebrow text-muted-foreground max-compact:hidden">
            {keyHint(options.length, multi)}
          </kbd>
          <Button type="button" variant="ghost" size="sm" disabled={stopping} onClick={onStop}>
            {stopping ? "Stopping…" : "Stop run"}
          </Button>
        </span>
      </div>
      <div>
        {options.map((option, index) => (
          <OptionRow
            key={option.id}
            option={option}
            position={index + 1}
            multi={multi}
            checked={checked.includes(option.id)}
            disabled={disabled}
            onSelect={select}
          />
        ))}
        {allowFreeText ? (
          <button
            type="button"
            disabled={disabled}
            aria-keyshortcuts={OTHER_KEY}
            onClick={onOther}
            className="grid w-full grid-cols-[auto_1fr] items-center gap-2.5 border-t py-1.75 pr-3 pl-5 text-left transition-colors hover:bg-accent relative before:absolute before:inset-y-0 before:left-0 before:w-0 before:bg-foreground focus-visible:before:w-0.5 focus-visible:bg-accent focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 max-guides:pl-4"
          >
            <KeyBox label={OTHER_KEY} checked={false} multi={false} />
            <span className="text-body text-muted-foreground">Something else, let me type it</span>
          </button>
        ) : null}
      </div>
      {multi ? (
        <div className="flex justify-end gap-2 border-t px-3 py-2">
          <Button type="button" variant="outline" size="sm" disabled={disabled || checked.length === 0} onClick={() => setChecked([])}>
            Clear
          </Button>
          <Button type="button" size="sm" disabled={disabled || checked.length === 0} onClick={() => onPick(checked)}>
            Continue ({checked.length})
          </Button>
        </div>
      ) : null}
    </div>
  );
}
