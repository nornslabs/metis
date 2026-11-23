const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;
const WEEK_DAYS = 7;
const MONTH_DAYS = 30;
const YEAR_DAYS = 365;

function plural(count: number, unit: string): string {
  return `${count} ${unit}${count === 1 ? "" : "s"} ago`;
}

/** "just now", "5 min ago", "3 hours ago", "2 days ago", "3 weeks ago", "1 month ago". */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const elapsed = now.getTime() - new Date(iso).getTime();
  if (elapsed < MINUTE_MS) return "just now";
  if (elapsed < HOUR_MS) return `${Math.floor(elapsed / MINUTE_MS)} min ago`;
  if (elapsed < DAY_MS) return plural(Math.floor(elapsed / HOUR_MS), "hour");
  const days = Math.floor(elapsed / DAY_MS);
  if (days < WEEK_DAYS) return plural(days, "day");
  if (days < MONTH_DAYS) return plural(Math.floor(days / WEEK_DAYS), "week");
  if (days < YEAR_DAYS) return plural(Math.floor(days / MONTH_DAYS), "month");
  return plural(Math.floor(days / YEAR_DAYS), "year");
}
