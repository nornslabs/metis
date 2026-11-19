import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

type ProviderKeys = components["schemas"]["ProviderKeys"];

/** Why the LLM key blocks a run: the same values as the server's `provider.llm_not_ready` `meta.reason`. */
export type LlmBlock = "not_configured" | "not_tested" | "test_failed";

export type KeyReadiness = {
  /** Null when the LLM key exists and its last test passed. */
  readonly llmBlock: LlmBlock | null;
  readonly exaMissing: boolean;
};

/** Opens the settings sheet on the API keys tab. A link, not `useSearchParams`, so `/` still prerenders. */
export const KEYS_SETTINGS_HREF = "?settings=keys";

export const LLM_NOT_READY_CODE = "provider.llm_not_ready";

const BLOCK_MESSAGES: Readonly<Record<LlmBlock, string>> = {
  not_configured: "Add an LLM key to start.",
  not_tested: "Test your LLM key to start.",
  test_failed: "Your LLM key failed its last test.",
};

function isLlmBlock(value: unknown): value is LlmBlock {
  return typeof value === "string" && value in BLOCK_MESSAGES;
}

/** What the saved keys allow: whether a run may start, and whether research will be skipped. */
export function keyReadiness(keys: ProviderKeys): KeyReadiness {
  return { llmBlock: llmBlockOf(keys.llm), exaMissing: !keys.exa };
}

export function llmBlockMessage(reason: LlmBlock): string {
  return BLOCK_MESSAGES[reason];
}

/** The gate's text for a `402 provider.llm_not_ready`; null for any other error. */
export function llmNotReadyMessage(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.code !== LLM_NOT_READY_CODE) return null;
  const reason = error.meta.reason;
  return isLlmBlock(reason) ? llmBlockMessage(reason) : error.detail ?? error.title;
}

function llmBlockOf(llm: ProviderKeys["llm"]): LlmBlock | null {
  if (!llm) return "not_configured";
  if (llm.last_test_ok === null) return "not_tested";
  return llm.last_test_ok ? null : "test_failed";
}
