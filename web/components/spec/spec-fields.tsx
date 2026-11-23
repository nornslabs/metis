"use client";

import { useRef, useState, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";
import { joinItems } from "@/lib/spec/sections";

/** Hover, focus and padding of an editable region (sample `.spec [contenteditable]`). */
const FIELD_CLASS =
  "w-full resize-none border border-transparent bg-transparent px-1.5 py-1 text-control outline-none placeholder:text-muted-foreground hover:border-border focus:border-ring focus:bg-card";

const NOT_SET = "Not set";

function leaveOnEscape(event: KeyboardEvent<HTMLElement>): void {
  if (event.key === "Escape") event.currentTarget.blur();
}

interface FieldProps {
  label: string;
  placeholder: string;
  locked: boolean;
  /** Called with the section's new text on every change. */
  onChange: (text: string) => void;
}

/** A paragraph section: an editable text area, or plain text once the spec is locked. */
export function TextField({ label, placeholder, locked, initial, onChange }: FieldProps & { initial: string }) {
  const [value, setValue] = useState(initial);
  if (locked) {
    return <p className="px-1.5 text-control break-words whitespace-pre-wrap">{value || <Muted>{NOT_SET}</Muted>}</p>;
  }
  return (
    <textarea
      aria-label={label}
      value={value}
      rows={2}
      placeholder={placeholder}
      className={cn(FIELD_CLASS, "field-sizing-content min-h-9")}
      onChange={(event) => {
        setValue(event.target.value);
        onChange(event.target.value);
      }}
      onKeyDown={leaveOnEscape}
    />
  );
}

/** A bullet section: one line per item; Enter adds an item below, Backspace on an empty item removes it. */
export function ListField({ label, placeholder, locked, initial, onChange }: FieldProps & { initial: readonly string[] }) {
  const [items, setItems] = useState<readonly string[]>(initial.length > 0 ? initial : [""]);
  const inputs = useRef<(HTMLInputElement | null)[]>([]);
  const focusAfter = useRef<number | null>(null);

  if (locked) {
    const shown = items.filter((item) => item.trim() !== "");
    return shown.length === 0 ? (
      <p className="px-1.5 text-control text-muted-foreground">{NOT_SET}</p>
    ) : (
      <ul className="flex list-disc flex-col gap-0.5 pl-6 text-control">
        {shown.map((item, index) => (
          <li key={`${index}:${item}`} className="break-words">
            {item}
          </li>
        ))}
      </ul>
    );
  }

  const update = (next: readonly string[]) => {
    setItems(next);
    onChange(joinItems(next));
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>, index: number) => {
    if (event.key === "Enter") {
      event.preventDefault();
      focusAfter.current = index + 1;
      update([...items.slice(0, index + 1), "", ...items.slice(index + 1)]);
    } else if (event.key === "Backspace" && items[index] === "" && items.length > 1) {
      event.preventDefault();
      focusAfter.current = Math.max(0, index - 1);
      update(items.filter((_, position) => position !== index));
    } else {
      leaveOnEscape(event);
    }
  };

  return (
    <ul aria-label={label} className="flex flex-col gap-0.5">
      {items.map((item, index) => (
        <li key={index} className="flex items-center">
          <span aria-hidden="true" className="w-4 shrink-0 text-center text-muted-foreground">
            •
          </span>
          <input
            ref={(node) => {
              inputs.current[index] = node;
              if (node && focusAfter.current === index) {
                focusAfter.current = null;
                node.focus();
              }
            }}
            type="text"
            aria-label={`${label}, item ${index + 1}`}
            value={item}
            placeholder={items.length === 1 || index === items.length - 1 ? placeholder : undefined}
            className={FIELD_CLASS}
            onChange={(event) => update(items.map((current, position) => (position === index ? event.target.value : current)))}
            onKeyDown={(event) => onKeyDown(event, index)}
            onBlur={() => {
              // An empty row left behind is dropped (the last one stays as the placeholder row).
              if (item === "" && items.length > 1) setItems(items.filter((_, position) => position !== index));
            }}
          />
        </li>
      ))}
    </ul>
  );
}

function Muted({ children }: { children: string }) {
  return <span className="text-muted-foreground">{children}</span>;
}
