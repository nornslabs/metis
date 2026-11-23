import type { PlanSummary } from "@/lib/plan/view";

/** The four numbers at the top of the plan: phases, tasks, points, critical path (points). */
export function PlanSummaryStrip({ summary }: { summary: PlanSummary }) {
  const cells = [
    { label: "Phases", value: summary.phases },
    { label: "Tasks", value: summary.tasks },
    { label: "Points", value: summary.points },
    { label: "Critical path", value: summary.criticalPoints },
  ];
  return (
    <dl className="grid grid-cols-4 border-b">
      {cells.map((cell) => (
        <div key={cell.label} className="grid gap-0.5 px-3.5 py-3 not-first:border-l max-narrow:px-2.5 max-narrow:py-2.5">
          <dd className="order-first text-xl max-narrow:text-base font-semibold tracking-tight tabular-nums">{cell.value}</dd>
          <dt className="text-micro tracking-label text-muted-foreground uppercase">{cell.label}</dt>
        </div>
      ))}
    </dl>
  );
}
