import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import { getSTTClientProvider } from "./config";
import { WebSpeechSTTProvider } from "./providers";

const originalWindow = globalThis.window;
const originalNavigator = globalThis.navigator;

type MockWindow = {
  SpeechRecognition?: new () => unknown;
  webkitSpeechRecognition?: new () => unknown;
  [key: string]: unknown;
};

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  Object.defineProperty(globalThis, "window", { value: originalWindow, configurable: true });
  Object.defineProperty(globalThis, "navigator", { value: originalNavigator, configurable: true });
});

describe("getSTTClientProvider", () => {
  it("returns WebSpeechSTTProvider when SpeechRecognition is available", () => {
    Object.defineProperty(globalThis, "window", {
      value: { SpeechRecognition: class {} } as MockWindow,
      configurable: true,
    });
    const provider = getSTTClientProvider();
    expect(provider).toBeInstanceOf(WebSpeechSTTProvider);
  });

  it("returns WebSpeechSTTProvider when webkitSpeechRecognition is available", () => {
    Object.defineProperty(globalThis, "window", {
      value: { webkitSpeechRecognition: class {} } as MockWindow,
      configurable: true,
    });
    const provider = getSTTClientProvider();
    expect(provider).toBeInstanceOf(WebSpeechSTTProvider);
  });

  it("throws when Web Speech API is unavailable", () => {
    Object.defineProperty(globalThis, "window", { value: {} as MockWindow, configurable: true });
    expect(() => getSTTClientProvider()).toThrow("Web Speech API is not available");
  });

  it("throws outside browser (no window)", () => {
    Object.defineProperty(globalThis, "window", { value: undefined, configurable: true });
    expect(() => getSTTClientProvider()).toThrow("can only be used on the client");
  });
});
