import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import { getSTTProvider, type STTProvider } from "./factory";
import { getSTTServerConfig } from "./config.server";
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

  it("throws for unknown provider", () => {
    process.env.STT_PROVIDER = "bogus";
    expect(() => getSTTServerConfig()).toThrow();
  });

  it("throws when sarvam has no API key", () => {
    process.env.STT_PROVIDER = "sarvam";
    delete process.env.SARVAM_API_KEY;
    expect(() => getSTTServerConfig()).toThrow("SARVAM_API_KEY");
  });
});

describe("getSTTProvider", () => {
  it("returns a SarvamSTTProvider instance when provider is sarvam with key", () => {
    process.env.STT_PROVIDER = "sarvam";
    process.env.SARVAM_API_KEY = "sk-test-key";
    const provider = getSTTProvider();
    expect(provider).toBeInstanceOf(SarvamSTTProvider);
  });

  it("auto-selects SarvamSTTProvider when SARVAM_API_KEY set (even if STT_PROVIDER=web-speech)", () => {
    process.env.STT_PROVIDER = "web-speech";
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
    process.env.STT_PROVIDER = "bogus";
    expect(() => getSTTProvider()).toThrow();
  });

  it("SarvamSTTProvider throws when no API key configured", () => {
    process.env.STT_PROVIDER = "sarvam";
    delete process.env.SARVAM_API_KEY;
    expect(() => getSTTProvider()).toThrow("SARVAM_API_KEY");
  });
});