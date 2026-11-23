import { getSTTServerConfig } from "./config.server";
import { MockSTTProvider } from "./providers";
import { SarvamSTTProvider } from "./providers";
import { WebSpeechSTTProvider } from "./providers";
import type { STTProvider } from "./types";
export type { STTProvider };

/** Factory: returns the STT provider configured by STT_PROVIDER env.
 *
 * Provider selection:
 * - `sarvam`    -> SarvamSTTProvider (requires SARVAM_API_KEY)
 * - `web-speech` -> WebSpeechSTTProvider (free, browser built-in)
 * - `mock`      -> MockSTTProvider (tests only)
 *
 * Throws a clear error for unknown providers or missing credentials.
 */
export function getSTTProvider(): STTProvider {
  const config = getSTTServerConfig();

  switch (config.provider) {
    case "mock":
      return new MockSTTProvider();
    case "web-speech":
      return new WebSpeechSTTProvider();
    case "sarvam":
      if (!config.sarvamApiKey) {
        throw new Error(
          "SARVAM_API_KEY is required when STT_PROVIDER=sarvam. Set SARVAM_API_KEY in .env, or use STT_PROVIDER=web-speech for a free fallback.",
        );
      }
      return new SarvamSTTProvider(config.sarvamApiKey);
    default:
      const _exhaustive: never = config.provider;
      throw new Error(`Unknown STT provider: ${config.provider}`);
  }
}
