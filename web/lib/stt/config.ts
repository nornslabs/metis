import type { STTProviderName } from "./types";

/** Client-safe STT config: provider name only, no secrets. Safe to import from client components. */
export function getSTTClientConfig(): { provider: STTProviderName } {
  return {
    provider: (process.env.NEXT_PUBLIC_STT_PROVIDER ?? "web-speech") as STTProviderName,
  };
}
