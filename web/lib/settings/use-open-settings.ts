"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import { withSettingsTab, type SettingsTab } from "./tab";

/** Opens (or retargets) the settings sheet on the current route by setting `?settings=<tab>`. */
export function useOpenSettings(): (tab: SettingsTab) => void {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  return useCallback(
    (tab) => router.replace(withSettingsTab(pathname, new URLSearchParams(search), tab)),
    [router, pathname, search],
  );
}
