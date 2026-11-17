export const SETTINGS_TABS = ["account", "keys", "integrations", "prefs"] as const;
export type SettingsTab = (typeof SETTINGS_TABS)[number];

export const SETTINGS_PARAM = "settings";
const DEFAULT_TAB: SettingsTab = "account";

/** The tab named by `?settings=`: null when the param is absent (sheet closed), `account` when unknown. */
export function parseSettingsTab(value: string | null): SettingsTab | null {
  if (value === null) return null;
  return SETTINGS_TABS.find((tab) => tab === value) ?? DEFAULT_TAB;
}

/** The same URL with `?settings=` set to `tab`, or removed when `tab` is null. Other params stay. */
export function withSettingsTab(
  pathname: string,
  search: URLSearchParams,
  tab: SettingsTab | null,
): string {
  const next = new URLSearchParams(search);
  if (tab === null) next.delete(SETTINGS_PARAM);
  else next.set(SETTINGS_PARAM, tab);
  const query = next.toString();
  return query === "" ? pathname : `${pathname}?${query}`;
}
