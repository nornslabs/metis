import type { STTProviderName } from "./types";

/** Client-safe STT config: provider name only, no secrets. Safe to import from client components. */
export function getSTTClientConfig(): { provider: STTProviderName } {
  // Provider selection happens server-side via getSTTProvider() reading STT_PROVIDER.
  // The client config defaults to web-speech (the free fallback); the server side
  // may override with sarvam when SARVAM_API_KEY is configured.
  return { provider: "web-speech" as STTProviderName };
}