import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import { getSTTProvider, type STTProvider } from "./factory";
import { getSTTServerConfig } from "./config.server";
import { MockSTTProvider } from "./providers";
import { SarvamSTTProvider } from "./providers";
import { WebSpeechSTTProvider } from "./providers";

// Mock process.env for each test
const originalEnv = process.env;

beforeEach(() => {
  vi.restoreAllMocks();
  process.env = { ...originalEnv };
});

afterEach(() => {
  process.env = originalEnv;
});

describe("getSTTServerConfig", () => {
  it("defaults to web-speech when STT_PROVIDER is unset", () => {
    delete process.env.STT_PROVIDER;
    delete process.env.SARVAM_API_KEY;
    const config = getSTTServerConfig();
    expect(config.provider).toBe("web-speech");
    expect(config.sarvamApiKey).toBeUndefined();
  });

  it("returns sarvam when STT_PROVIDER=sarvam", () => {
    process.env.STT_PROVIDER = "sarvam";
    process.env.SARVAM_API_KEY = "sk-test-key";
    const config = getSTTServerConfig();
    expect(config.provider).toBe("sarvam");
    expect(config.sarvamApiKey).toBe("sk-test-key");
  });

  it("returns mock when STT_PROVIDER=mock", () => {
    process.env.STT_PROVIDER = "mock";
    const config = getSTTServerConfig();
    expect(config.provider).toBe("mock");
  });

  it("throws for unknown provider", () => {
    process.env.STT_PROVIDER = "bogus" as any;
    expect(() => getSTTServerConfig()).toThrow();
  });

  it("throws when sarvam has no API key", () => {
    process.env.STT_PROVIDER = "sarvam";
    delete process.env.SARVAM_API_KEY;
    expect(() => getSTTServerConfig()).toThrow("SARVAM_API_KEY");
  });
});

describe("getSTTProvider", () => {
  it("returns a MockSTTProvider instance when provider is mock", () => {
    process.env.STT_PROVIDER = "mock";
    const provider = getSTTProvider();
    expect(provider).toBeInstanceOf(MockSTTProvider);
  });

  it("returns a SarvamSTTProvider instance when provider is sarvam with key", () => {
    process.env.STT_PROVIDER = "sarvam";
    process.env.SARVAM_API_KEY = "sk-test-key";
    const provider = getSTTProvider();
    expect(provider).toBeInstanceOf(SarvamSTTProvider);
  });

  it("returns a WebSpeechSTTProvider instance when provider is web-speech", () => {
    process.env.STT_PROVIDER = "web-speech";
    const provider = getSTTProvider();
    expect(provider).toBeInstanceOf(WebSpeechSTTProvider);
  });

  it("throws a clear error for unknown provider (via config validation)", () => {
    process.env.STT_PROVIDER = "bogus" as any;
    expect(() => getSTTProvider()).toThrow();
  });

  it("MockSTTProvider returns a configurable transcript", async () => {
    process.env.STT_PROVIDER = "mock";
    const provider = getSTTProvider() as MockSTTProvider;
    const blob = new Blob(["fake-audio"], { type: "audio/webm" });

    // Default transcript
    const defaultResult = await provider.transcribe(blob);
    expect(defaultResult).toBe("This is a mock transcription.");

    // Custom transcript
    const customProvider = new MockSTTProvider("custom transcript");
    const customResult = await customProvider.transcribe(blob);
    expect(customResult).toBe("custom transcript");

    // Deterministic: same input returns same output
    const result1 = await provider.transcribe(blob);
    const result2 = await provider.transcribe(blob);
    expect(result1).toBe(result2);
  });

  it("SarvamSTTProvider throws when no API key configured", () => {
    process.env.STT_PROVIDER = "sarvam";
    delete process.env.SARVAM_API_KEY;
    expect(() => getSTTProvider()).toThrow("SARVAM_API_KEY");
  });
});