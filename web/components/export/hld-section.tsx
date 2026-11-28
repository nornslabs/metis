"use client";

import { ChevronRight } from "lucide-react";
import { useId, useState } from "react";

import { SafeMarkdown } from "@/components/chat/safe-markdown";
import { Skeleton } from "@/components/ui/skeleton";
import { useSpec } from "@/lib/api/queries/use-spec";
import { cn } from "@/lib/cn";
import { hldComponentNames } from "@/lib/export/hld";
import { actionLabel } from "@/lib/export/preview-lines";
import type { PreviewHld } from "@/lib/schemas/export";

interface HldSectionProps {
  ideaId: string;
  hld: PreviewHld;
}

/** The HLD the export saves, read only: its title, language, components and full text. */
export function HldSection({ ideaId, hld }: HldSectionProps) {
  const spec = useSpec(ideaId, true);
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const text = spec.data?.hld ?? null;
  const components = text ? hldComponentNames(text.content_md) : [];
  return (
    <section aria-label="HLD" className="grid gap-1.5 border-b py-1.5 text-control">
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 break-words">
          <span className="text-muted-foreground">HLD</span> · {hld.title}
        </span>
        <span className="shrink-0 text-meta text-muted-foreground">{actionLabel(hld.action)}</span>
      </div>
      {spec.isPending ? <Skeleton className="h-4 w-2/3" /> : null}
      {spec.isError || (spec.isSuccess && text === null) ? (
        <p className="text-meta text-muted-foreground">HLD text unavailable.</p>
      ) : null}
      {text ? (
        <>
          {text.stale ? <p className="text-meta text-warning">The HLD was written for an earlier spec.</p> : null}
          <p className="text-meta text-muted-foreground">Language · {text.build_language}</p>
          {components.length > 0 ? (
            <ul aria-label="Components" className="flex flex-wrap gap-1">
              {components.map((name) => (
                <li key={name} className="border px-1 text-meta">
                  {name}
                </li>
              ))}
            </ul>
          ) : null}
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((value) => !value)}
            className="inline-flex w-fit items-center gap-1 text-meta focus-visible:underline focus-visible:outline-none"
          >
            <ChevronRight size={12} aria-hidden="true" className={cn("transition-transform", open && "rotate-90")} />
            Read the HLD
          </button>
          {open ? (
            <div id={panelId} className="flex flex-col gap-1.5 text-note break-words">
              <SafeMarkdown text={text.content_md} />
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
