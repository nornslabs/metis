import { expect, test, type Page } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { seedTestedLlmKey, removeSeededLlmKey } from "./support/keys";

const RUN_TIMEOUT = 30_000;

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
  await context.request.get("/v1/workspaces/current");
  seedTestedLlmKey();
});

test.afterAll(() => removeSeededLlmKey());

test.describe("voice input", () => {
  test("voice button renders on chat page", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Your idea").fill("Voice test idea");
    await page.getByRole("button", { name: "Start" }).click();
    await page.waitForURL(/^\/ideas\//);
    await expect(page.getByRole("button", { name: /Start voice recording/ })).toBeVisible();
  });

  test("voice button hidden when Web Speech API not supported", async ({ page, context }) => {
    // Block Web Speech API
    await context.addInitScript(() => {
      Object.defineProperty(window, "SpeechRecognition", { value: undefined, configurable: true });
      Object.defineProperty(window, "webkitSpeechRecognition", { value: undefined, configurable: true });
    });
    await page.goto("/");
    await page.getByLabel("Your idea").fill("No speech API");
    await page.getByRole("button", { name: "Start" }).click();
    await page.waitForURL(/^\/ideas\//);
    await expect(page.getByRole("button", { name: /Start voice recording/ })).toHaveCount(0);
  });

  test("empty transcript shows Nothing heard toast", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Your idea").fill("Empty transcript test");
    await page.getByRole("button", { name: "Start" }).click();
    await page.waitForURL(/^\/ideas\//);
    await page.getByRole("button", { name: /Start voice recording/ }).click();
    await page.getByRole("button", { name: /Stop recording/ }).click();
    await expect(page.getByText(/Nothing heard/)).toBeVisible({ timeout: 5000 });
  });

  test("transcript appears in input field after voice input", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Your idea").fill("Voice transcript test");
    await page.getByRole("button", { name: "Start" }).click();
    await page.waitForURL(/^\/ideas\//);
    await page.getByRole("button", { name: /Start voice recording/ }).click();
    await page.getByRole("button", { name: /Stop recording/ }).click();
    // The input field should contain a transcript (mock provider returns fixed text)
    await expect(page.locator("textarea[name=\"text\"]")).not.toBeEmpty({ timeout: 5000 });
  });

  test("STT error shows Transcription failed toast", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Your idea").fill("STT error test");
    await page.getByRole("button", { name: "Start" }).click();
    await page.waitForURL(/^\/ideas\//);
    await page.getByRole("button", { name: /Start voice recording/ }).click();
    await page.getByRole("button", { name: /Stop recording/ }).click();
    await expect(page.getByText(/Transcription failed/)).toBeVisible({ timeout: 5000 });
  });

  test("touch targets ≥44px on mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 813 }); // iPhone SE size
    await page.goto("/");
    await page.getByLabel("Your idea").fill("Mobile voice test");
    await page.getByRole("button", { name: "Start" }).click();
    await page.waitForURL(/^\/ideas\//);
    const voiceButton = page.getByRole("button", { name: /Start voice recording/ });
    await expect(voiceButton).toBeVisible();
    const box = await voiceButton.boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(44);
    expect(box?.height).toBeGreaterThanOrEqual(44);
  });
});
