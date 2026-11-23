"use client";

import { ChevronRight } from "lucide-react";
import { useEffect, useId, useState, type CSSProperties } from "react";

import { Cite } from "@/components/panel/cite";
import { SourceLink } from "@/components/research/source-link";
import { cn } from "@/lib/cn";
import { confidenceLabel } from "@/lib/research/view";
import { isWeakMark } from "@/lib/scores/versions";
import { MAX_RAW, PARAM_LABELS, barPercent, formatPoints, type ScoreParamResult } from "@/lib/scores/view";

/** The bar fills from empty on its first paint (800 ms); `motion-reduce` shows it filled at once. */
function useFilled(): boolean {
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setFilled(true));
    return () => cancelAnimationFrame(frame);
  }, []);
  return filled;
}

function Evidence({ param }: { param: ScoreParamResult }) {
  if (param.no_evidence || param.evidence.length === 0) {
    return <p className="text-control text-muted-foreground">No evidence: this mark is a guess.</p>;
  }
  return (
    <ul className="flex flex-col gap-1.5">
      {param.evidence.map((item) => (
        <li key={`${item.url}:${item.title}`} className="flex flex-col gap-0.5">
          <span className="text-control break-words">
            {item.title} <Cite url={item.url} />
          </span>
          {item.quote ? (
            <blockquote className="border-l-2 pl-2 text-control break-words text-muted-foreground">{item.quote}</blockquote>
          ) : null}
          <SourceLink url={item.url} />
        </li>
      ))}
    </ul>
  );
}

/** One rubric parameter: label and weight, a mark bar, points; opens to the reason, evidence and confidence. */
export function ParamBar({ param }: { param: ScoreParamResult }) {
  const [open, setOpen] = useState(false);
  const filled = useFilled();
  const panelId = useId();
  const label = PARAM_LABELS[param.param];
  const weak = isWeakMark(param.raw);
  return (
    <li className="flex flex-col">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`${label}: ${param.raw} out of ${MAX_RAW}, ${formatPoints(param.weighted)} of ${param.weight} points`}
        onClick={() => setOpen((current) => !current)}
        className="grid grid-cols-param-row items-center gap-2.5 py-1 text-left text-control hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        <span className="flex min-w-0 items-center gap-1 text-muted-foreground">
          <ChevronRight size={12} aria-hidden="true" className={cn("shrink-0 transition-transform motion-reduce:transition-none", open && "rotate-90")} />
          <span className="truncate">{label}</span>
          <span className="shrink-0 text-micro">{param.weight}%</span>
        </span>
        <span className="h-1 bg-muted" aria-hidden="true">
          <span
            className={cn(
              "block h-full transition-[width] duration-800 ease-out motion-reduce:transition-none",
              weak ? "bg-warning" : "bg-primary",
              filled ? "w-(--bar)" : "w-0 motion-reduce:w-(--bar)",
            )}
            style={{ "--bar": `${barPercent(param.raw)}%` } as CSSProperties}
          />
        </span>
        <span className={cn("text-right font-medium tabular-nums", weak && "text-warning")}>{barPercent(param.raw)}</span>
      </button>
      {open ? (
        <div id={panelId} className="mb-1 ml-4 flex flex-col gap-1.5 border-l pl-2.5">
          <p className="text-control break-words whitespace-pre-wrap">{param.reason}</p>
          <p className="text-meta text-muted-foreground">
            Confidence: {confidenceLabel(param.confidence)} ({param.confidence.toFixed(2)})
          </p>
          <Evidence param={param} />
        </div>
      ) : null}
    </li>
  );
}
