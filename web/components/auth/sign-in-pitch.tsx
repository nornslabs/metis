import type { CSSProperties } from "react";

const STEPS = [
  { number: "01", label: "Interview" },
  { number: "02", label: "Research & score" },
  { number: "03", label: "Plan to Linear" },
] as const;

const SAMPLE_BARS = [
  { label: "Problem severity", percent: 78 },
  { label: "Uniqueness", percent: 42 },
  { label: "Market demand", percent: 74 },
] as const;

export function SignInPitch() {
  return (
    <section className="flex flex-col justify-center gap-badge border-r px-8 py-10 max-stacked:border-r-0 max-stacked:px-6 max-stacked:py-7 max-compact:px-4 max-compact:py-6">
      <span className="font-mono text-eyebrow uppercase tracking-eyebrow text-muted-foreground">
        Idea → Score → Plan
      </span>
      <h1 className="max-w-headline text-display font-semibold">
        Know if your idea is worth building before you build it.
      </h1>
      <p className="max-w-lead text-body text-muted-foreground">
        Metis interviews you, researches the market with sources, scores the
        idea on six fixed criteria and turns it into a Linear plan.
      </p>

      <ol className="grid max-w-pitch grid-cols-3 border max-compact:grid-cols-1">
        {STEPS.map((step) => (
          <li
            key={step.number}
            className="grid gap-0.5 px-2.5 py-2 not-first:border-l max-compact:not-first:border-t max-compact:not-first:border-l-0"
          >
            <b className="font-mono text-micro font-medium text-muted-foreground">
              {step.number}
            </b>
            <span className="text-xs font-medium">{step.label}</span>
          </li>
        ))}
      </ol>

      <div
        aria-hidden="true"
        className="max-w-pitch border bg-card max-stacked:hidden"
      >
        <div className="flex items-center justify-between border-b px-2.5 py-1.5 text-meta text-muted-foreground">
          <span>Latest score</span>
          <b className="font-mono font-medium text-foreground">PROMISING</b>
        </div>
        <div className="grid grid-cols-[auto_1fr] items-center gap-3.5 p-2.5">
          <div className="text-score leading-none font-semibold tracking-score tabular-nums">
            67
            <small className="text-meta font-normal tracking-normal text-muted-foreground">
              {" "}
              /100
            </small>
          </div>
          <div className="grid gap-1.5">
            {SAMPLE_BARS.map((bar) => (
              <div
                key={bar.label}
                className="grid grid-cols-score-row items-center gap-2.5 text-eyebrow text-muted-foreground"
              >
                {bar.label}
                <span className="h-track bg-muted">
                  <i
                    className="block h-full w-(--bar) bg-foreground"
                    style={{ "--bar": `${bar.percent}%` } as CSSProperties}
                  />
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
