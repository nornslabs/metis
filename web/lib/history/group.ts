export type ActivityGroup = "Today" | "This week" | "Earlier";

const GROUP_ORDER: readonly ActivityGroup[] = ["Today", "This week", "Earlier"];
const WEEK_DAYS = 7;

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** Today, the six days before it ("This week"), or Earlier, by the user's calendar days. */
export function activityGroup(iso: string, now: Date = new Date()): ActivityGroup {
  const today = startOfDay(now);
  const day = startOfDay(new Date(iso));
  if (day >= today) return "Today";
  const dayBefore = new Date(today);
  dayBefore.setDate(dayBefore.getDate() - (WEEK_DAYS - 1));
  return day >= dayBefore.getTime() ? "This week" : "Earlier";
}

export interface RowGroup<T> {
  group: ActivityGroup;
  rows: readonly T[];
}

/** Groups rows (already newest first) Today / This week / Earlier; empty groups are left out. */
export function groupByActivity<T extends { activeAt: string }>(
  rows: readonly T[],
  now: Date = new Date(),
): readonly RowGroup<T>[] {
  return GROUP_ORDER.map((group) => ({
    group,
    rows: rows.filter((row) => activityGroup(row.activeAt, now) === group),
  })).filter((entry) => entry.rows.length > 0);
}
