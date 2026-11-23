import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import { getSTTClientProvider } from "./config";
import { WebSpeechSTTProvider } from "./providers";

type SpeechRecognitionMock = {
  continuous: boolean;
  interimResults: boolean;
  onresult?: ((event: { results: { [index: number]: { [index: number]: { transcript: string } } } }) => void) | null;
  onerror?: ((event: { error: string }) => void) | null;
  onend?: (() => void) | null;
  start: () => void;
  stop: () => void;
};

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
      value: { SpeechRecognition: class {} } as Record<string, unknown>,
      configurable: true,
    });
    const provider = getSTTClientProvider();
    expect(typeof provider.transcribe).toBe("function");
  });

  it("WebSpeechSTTProvider.transcribe returns transcript from SpeechRecognition onresult", async () => {
    let onresultHandler: ((event: { results: { [index: number]: { [index: number]: { transcript: string } } } }) => void) | null = null;
    let onerrorHandler: ((event: { error: string }) => void) | null = null;

    Object.defineProperty(globalThis, "window", {
      value: {
        SpeechRecognition: class {
          continuous = false;
          interimResults = false;
          set onresult(h: ((event: { results: { [index: number]: { [index: number]: { transcript: string } } } }) => void) | null) {
            onresultHandler = h;
          }
          get onresult() {
            return onresultHandler;
          }
          set onerror(h: ((event: { error: string }) => void) | null) {
            onerrorHandler = h;
          }
          get onerror() {
            return onerrorHandler;
          }
          onend: (() => void) | null = null;
          start() {
            setTimeout(() => {
              onresultHandler?.({
                results: [[{ transcript: "hello world" }]],
              } as { results: { [index: number]: { [index: number]: { transcript: string } } } });
            }, 10);
          }
          stop() {}
        },
      } as Record<string, unknown>,
      configurable: true,
    });

    const provider = new WebSpeechSTTProvider();
    const result = await provider.transcribe(new Blob(["audio"], { type: "audio/webm" }));
    expect(result).toBe("hello world");
  });

  it("WebSpeechSTTProvider.transcribe rejects when SpeechRecognition errors", async () => {
    let onerrorHandler: ((event: { error: string }) => void) | null = null;

    Object.defineProperty(globalThis, "window", {
      value: {
        SpeechRecognition: class {
          continuous = false;
          interimResults = false;
          onresult: ((event: { results: { [index: number]: { [index: number]: { transcript: string } } } }) => void) | null = null;
          set onerror(h: ((event: { error: string }) => void) | null) {
            onerrorHandler = h;
          }
          get onerror() {
            return onerrorHandler;
          }
          onend: (() => void) | null = null;
          start() {
            setTimeout(() => {
              onerrorHandler?.({ error: "no-speech" });
            }, 10);
          }
          stop() {}
        },
      } as Record<string, unknown>,
      configurable: true,
    });

    const provider = new WebSpeechSTTProvider();
    await expect(provider.transcribe(new Blob(["audio"], { type: "audio/webm" }))).rejects.toThrow(
      "Web Speech API error",
    );
  });

  it("throws when Web Speech API is unavailable", () => {
    Object.defineProperty(globalThis, "window", { value: {} as Record<string, unknown>, configurable: true });
    expect(() => getSTTClientProvider()).toThrow("Web Speech API is not available");
  });
});
