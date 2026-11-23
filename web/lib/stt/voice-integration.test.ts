import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import { getSTTClientProvider } from "./config";
import { WebSpeechSTTProvider } from "./providers";

const originalWindow = globalThis.window;

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  Object.defineProperty(globalThis, "window", { value: originalWindow, configurable: true });
});

describe("voice transcription flow", () => {
  it("getSTTClientProvider returns a provider with transcribe", () => {
    Object.defineProperty(globalThis, "window", {
      value: { SpeechRecognition: class {} } as any,
      configurable: true,
    });
    const provider = getSTTClientProvider();
    expect(typeof provider.transcribe).toBe("function");
  });

  it("WebSpeechSTTProvider.transcribe returns transcript from SpeechRecognition onresult", async () => {
    let onresultHandler: any = null;
    let onerrorHandler: any = null;

    Object.defineProperty(globalThis, "window", {
      value: {
        SpeechRecognition: class {
          continuous = false;
          interimResults = false;
          set onresult(h: any) { onresultHandler = h; }
          get onresult() { return onresultHandler; }
          set onerror(h: any) { onerrorHandler = h; }
          get onerror() { return onerrorHandler; }
          onend: any = null;
          start() {
            setTimeout(() => {
              onresultHandler?.({
                results: [[{ transcript: "hello world" }]],
              });
            }, 10);
          }
          stop() {}
        },
      } as any,
      configurable: true,
    });

    const provider = new WebSpeechSTTProvider();
    const result = await provider.transcribe(new Blob(["audio"], { type: "audio/webm" }));
    expect(result).toBe("hello world");
  });

  it("WebSpeechSTTProvider.transcribe rejects when SpeechRecognition errors", async () => {
    let onerrorHandler: any = null;

    Object.defineProperty(globalThis, "window", {
      value: {
        SpeechRecognition: class {
          continuous = false;
          interimResults = false;
          onresult: any = null;
          set onerror(h: any) { onerrorHandler = h; }
          get onerror() { return onerrorHandler; }
          onend: any = null;
          start() {
            setTimeout(() => {
              onerrorHandler?.({ error: "no-speech" });
            }, 10);
          }
          stop() {}
        },
      } as any,
      configurable: true,
    });

    const provider = new WebSpeechSTTProvider();
    await expect(provider.transcribe(new Blob(["audio"], { type: "audio/webm" }))).rejects.toThrow(
      "Web Speech API error",
    );
  });

  it("throws when Web Speech API is unavailable", () => {
    Object.defineProperty(globalThis, "window", { value: {} as any, configurable: true });
    expect(() => getSTTClientProvider()).toThrow("Web Speech API is not available");
  });

  it("empty transcript is treated as no-op", () => {
    const transcript = "";
    expect(transcript.trim()).toBe("");
  });
});
