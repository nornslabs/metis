import { z } from "zod";

/** The output panel's panes, in tab order. `?panel=` names one of them. */
export const OUTPUT_PANES = ["score", "research", "suggestions", "spec", "plan"] as const;
export type OutputPane = (typeof OUTPUT_PANES)[number];

export const PANEL_PARAM = "panel";

const outputPaneSchema = z.enum(OUTPUT_PANES);

/** The pane named by `?panel=`, or null when the param is absent or not a pane (no panel opens). */
export function parseOutputPane(value: string | null): OutputPane | null {
  const parsed = outputPaneSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

/** The same URL with `?panel=` set to `pane`, or removed when `pane` is null. Other params stay. */
export function withOutputPane(
  pathname: string,
  search: URLSearchParams,
  pane: OutputPane | null,
): string {
  const next = new URLSearchParams(search);
  if (pane === null) next.delete(PANEL_PARAM);
  else next.set(PANEL_PARAM, pane);
  const query = next.toString();
  return query === "" ? pathname : `${pathname}?${query}`;
}
