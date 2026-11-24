import { WebSpeechSTTProvider } from "./providers";
import type { STTProvider } from "./types";

/** Returns the STT provider for client-side use (Web Speech API only). */
export function getSTTClientProvider(): STTProvider {
  if (typeof window === "undefined") {
    throw new Error("getSTTClientProvider can only be used on the client");
  }

  if (!("SpeechRecognition" in window || "webkitSpeechRecognition" in window)) {
    throw new Error("Web Speech API is not available in this browser");
  }

  return new WebSpeechSTTProvider();
}
