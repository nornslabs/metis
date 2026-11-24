import { getSTTServerConfig } from "./config.server";
import { SarvamSTTProvider } from "./providers";
import { WebSpeechSTTProvider } from "./providers";
import type { STTProvider } from "./types";
export type { STTProvider };

/** Factory: returns the STT provider based on env configuration.
 *
 * Provider selection:
 * - `SARVAM_API_KEY` set    -> SarvamSTTProvider (requires SARVAM_API_KEY)
 * - otherwise               -> WebSpeechSTTProvider (free, browser built-in)
 *
 * Throws a clear error for unknown providers or missing credentials.
 */
export function getSTTProvider(): STTProvider {
  const config = getSTTServerConfig();

  if (config.sarvamApiKey) {
    return new SarvamSTTProvider(config.sarvamApiKey);
  }

  return new WebSpeechSTTProvider();
}
