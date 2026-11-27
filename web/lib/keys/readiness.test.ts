import { describe, expect, test } from "vitest";

import { ApiError } from "@/lib/api/errors";

import {
  isKillSwitchError,
  isKillSwitchRunError,
  keyReadiness,
  llmBlockMessage,
  llmNotReadyMessage,
} from "./readiness";

const view = (lastTestOk: boolean | null) => ({
  base_url: null,
  kind: "llm" as const,
  last_test_ok: lastTestOk,
  last_tested_at: null,
  masked: "sk-…a1b2",
  model: null,
  updated_at: "2026-11-19T00:00:00Z",
  version: 1,
});

describe("keyReadiness", () => {
  test("blocks as not_configured when no LLM key is saved", () => {
    expect(keyReadiness({}).llmBlock).toBe("not_configured");
    expect(keyReadiness({ llm: null }).llmBlock).toBe("not_configured");
  });

  test("blocks as not_tested when the key was never tested", () => {
    expect(keyReadiness({ llm: view(null) }).llmBlock).toBe("not_tested");
  });

  test("blocks as test_failed when the last test failed", () => {
    expect(keyReadiness({ llm: view(false) }).llmBlock).toBe("test_failed");
  });

  test("does not block a key whose last test passed", () => {
    expect(keyReadiness({ llm: view(true) }).llmBlock).toBeNull();
  });

  test("reports whether an Exa key is missing", () => {
    expect(keyReadiness({ llm: view(true) }).exaMissing).toBe(true);
    expect(keyReadiness({ llm: view(true), exa: { ...view(true), kind: "exa" } }).exaMissing).toBe(false);
  });
});

describe("llmBlockMessage", () => {
  test("names each reason differently", () => {
    const messages = (["not_configured", "not_tested", "test_failed"] as const).map(llmBlockMessage);
    expect(new Set(messages).size).toBe(3);
  });
});

describe("llmNotReadyMessage", () => {
  const problem = (code: string, meta: Record<string, unknown> = {}) =>
    new ApiError({ status: 402, code, title: "Not ready", detail: "Server detail", meta });

  test("maps the server's reason to the same text as the gate", () => {
    expect(llmNotReadyMessage(problem("provider.llm_not_ready", { reason: "not_tested" }))).toBe(
      llmBlockMessage("not_tested"),
    );
  });

  test("falls back to the server's detail for an unknown reason", () => {
    expect(llmNotReadyMessage(problem("provider.llm_not_ready", { reason: "odd" }))).toBe("Server detail");
  });

  test("returns null for any other error", () => {
    expect(llmNotReadyMessage(problem("run.already_running"))).toBeNull();
    expect(llmNotReadyMessage(new Error("boom"))).toBeNull();
  });
});

describe("isKillSwitchError", () => {
  test("detects provider.not_configured with reason=kill_switch", () => {
    const err = new ApiError({
      status: 503,
      code: "provider.not_configured",
      title: "Provider Not Configured",
      meta: { provider: "llm", reason: "kill_switch" },
    });
    expect(isKillSwitchError(err)).toBe(true);
  });

  test("ignores missing-key provider.not_configured and other errors", () => {
    const missingKey = new ApiError({
      status: 400,
      code: "provider.not_configured",
      title: "Provider Not Configured",
      meta: { provider: "llm" },
    });
    expect(isKillSwitchError(missingKey)).toBe(false);
    expect(isKillSwitchError(new Error("boom"))).toBe(false);
  });
});

describe("isKillSwitchRunError", () => {
  test("detects kill switch run errors from worker", () => {
    expect(
      isKillSwitchRunError({
        code: "provider.not_configured",
        message: "LLM calls are disabled: the `llm_enabled` kill switch is off.",
      }),
    ).toBe(true);
    expect(isKillSwitchRunError({ code: "provider.not_configured", message: "No key" })).toBe(false);
    expect(isKillSwitchRunError(null)).toBe(false);
  });
});
