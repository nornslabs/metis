"use client";

import { keyReadiness, type KeyReadiness } from "@/lib/keys/readiness";

import { useSettings } from "./use-settings";

const OPEN: KeyReadiness = { llmBlock: null, exaMissing: false };

/**
 * What the workspace's saved keys allow. While settings load, or when they fail to load, nothing
 * is blocked and no banner shows: the server refuses a start anyway (`provider.llm_not_ready`).
 */
export function useKeyGate(): KeyReadiness {
  const { data } = useSettings();
  return data ? keyReadiness(data.keys) : OPEN;
}
