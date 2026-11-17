"use client";

import { useEffect } from "react";

import { useOpenSettings } from "@/lib/settings/use-open-settings";

/** ⌘, (Ctrl+, off macOS) opens the settings sheet from any app route. Renders nothing. */
export function SettingsShortcut() {
  const openSettings = useOpenSettings();
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "," || !(event.metaKey || event.ctrlKey) || event.altKey) return;
      event.preventDefault();
      openSettings("account");
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [openSettings]);
  return null;
}
