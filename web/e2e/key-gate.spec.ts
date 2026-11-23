import { expect, test, type Page } from "@playwright/test";

import { eventStreamBody, seedQueuedRun } from "./support/runs";
import { SESSION_COOKIE, createSessionToken } from "./support/session";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };

type KeyView = {
  base_url: string | null;
  kind: "llm" | "exa";
  last_test_ok: boolean | null;
  last_tested_at: string | null;
  masked: string;
  model: string | null;
  updated_at: string;
  version: number;
};
type Keys = { llm?: KeyView | null; exa?: KeyView | null };

const keyView = (kind: "llm" | "exa", lastTestOk: boolean | null): KeyView => ({
  base_url: null,
  kind,
  last_test_ok: lastTestOk,
  last_tested_at: null,
  masked: "sk-…e2e0",
  model: null,
  updated_at: "2026-11-19T00:00:00Z",
  version: 1,
});

const READY: Keys = { llm: keyView("llm", true), exa: keyView("exa", true) };
const NO_EXA: Keys = { llm: keyView("llm", true) };

/**
 * Answers `GET /v1/settings` with the given saved keys (read at each call) and default limits. No
 * real call is made, so no request is left in flight when a test ends.
 */
async function fakeKeys(page: Page, keys: () => Keys) {
  await page.route("**/v1/settings", (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return route.fulfill({
      json: { keys: keys(), settings: { max_steps: 50, run_budget_usd: 2, version: 0 } },
    });
  });
}

async function refuseStart(page: Page, reason: string) {
  await page.route("**/v1/ideas/*/runs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 402,
      contentType: "application/problem+json",
      json: {
        title: "LLM key not ready",
        code: "provider.llm_not_ready",
        detail: "Server detail",
        retryable: false,
        meta: { reason },
      },
    });
  });
}

async function createIdea(page: Page): Promise<{ id: string; workspace_id: string }> {
  const text = `E2E gate ${Date.now()}\nA longer description idea for test.`;
  const response = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title: text.split("\n")[0], raw_text: text },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

test.describe("LLM key gate", () => {
  test("no LLM key blocks Send, names the reason and links to the keys tab", async ({ page }) => {
    await fakeKeys(page, () => ({}));
    await page.goto("/");
    await page.getByLabel("Your idea").fill("A habit tracker for remote teams");
    await expect(page.getByText("Add an LLM key to start.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
    await page.getByRole("link", { name: "Open API keys" }).click();
    await expect(page).toHaveURL(/settings=keys/);
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
  });

  for (const [label, lastTestOk, message] of [
    ["an untested key", null, "Test your LLM key to start."],
    ["a key that failed its test", false, "Your LLM key failed its last test."],
  ] as const) {
    test(`${label} blocks Send`, async ({ page }) => {
      await fakeKeys(page, () => ({ llm: keyView("llm", lastTestOk) }));
      await page.goto("/");
      await page.getByLabel("Your idea").fill("A habit tracker for remote teams");
      await expect(page.getByText(message)).toBeVisible();
      await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
    });
  }

  test("testing the key in the settings sheet lifts the block without a reload", async ({ page }) => {
    let tested = false;
    await fakeKeys(page, () => ({ llm: keyView("llm", tested ? true : null), exa: keyView("exa", true) }));
    await page.route("**/v1/settings/keys/llm/test", async (route) => {
      tested = true;
      await route.fulfill({ status: 200, contentType: "application/json", json: { ok: true } });
    });
    await page.goto("/?settings=keys");
    await expect(page.getByText("Test your LLM key to start.")).toBeVisible();
    await page.getByRole("dialog", { name: "Settings" }).getByRole("button", { name: "Test" }).first().click();
    await expect(page.getByText("Test your LLM key to start.")).toHaveCount(0);
  });

  test("a 402 on the first run keeps the idea and offers the keys link", async ({ page }) => {
    await fakeKeys(page, () => READY);
    await refuseStart(page, "not_tested");
    await page.goto("/");
    await page.getByLabel("Your idea").fill("A habit tracker for remote teams");
    await page.getByLabel("Your idea").press("Enter");
    await page.waitForURL(/\/ideas\/[0-9a-f-]+$/);
    await expect(page.getByText("Test your LLM key to start.")).toBeVisible();
    // The toast's action is a button; it opens the keys tab on the idea page.
    await page.getByRole("button", { name: "Open API keys" }).click();
    await expect(page).toHaveURL(/\/ideas\/[0-9a-f-]+\?settings=keys$/);
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
  });

  test("Start on an idea with no run is blocked, then shows the server's reason on a 402", async ({ page }) => {
    const idea = await createIdea(page);
    let keys: Keys = {};
    await fakeKeys(page, () => keys);
    await page.goto(`/ideas/${idea.id}`);
    await expect(page.getByRole("button", { name: "Start" })).toBeDisabled();
    await expect(page.getByText("Add an LLM key to start.")).toBeVisible();

    keys = READY;
    await refuseStart(page, "test_failed");
    await page.reload();
    await page.getByRole("button", { name: "Start" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "Your LLM key failed its last test." })).toBeVisible();
  });
});

test.describe("Exa banner", () => {
  test("shows when only the Exa key is missing", async ({ page }) => {
    await fakeKeys(page, () => NO_EXA);
    await page.goto("/");
    await expect(page.getByText(/skip research: Exa isn't set up/)).toBeVisible();
    await expect(page.getByLabel("Your idea")).toBeEditable();
  });

  test("is absent when both keys are ready", async ({ page }) => {
    await fakeKeys(page, () => READY);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "What are you building?" })).toBeVisible();
    await expect(page.getByText(/skip research/)).toHaveCount(0);
  });

  test("is not shown while settings fail to load, and nothing is blocked", async ({ page }) => {
    await page.route("**/v1/settings", (route) =>
      route.request().method() === "GET" ? route.fulfill({ status: 500, json: {} }) : route.fallback(),
    );
    await page.goto("/");
    await page.getByLabel("Your idea").fill("A habit tracker for remote teams");
    await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
    await expect(page.getByText(/skip research/)).toHaveCount(0);
  });
});

test.describe("research skipped notice", () => {
  test("shows the notice and a skipped step, also after a reload", async ({ page }) => {
    const idea = await createIdea(page);
    const runId = seedQueuedRun(idea.id, idea.workspace_id);
    await page.route(`**/v1/runs/${runId}/events**`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: eventStreamBody(runId, [
          { type: "run_status", data: { status: "running" } },
          { type: "node_started", data: { node: "researcher" } },
          {
            type: "notice",
            data: { code: "research.skipped_no_exa", text: "Research is skipped: Exa isn't set up." },
          },
          { type: "node_finished", data: { node: "researcher" } },
          { type: "run_status", data: { status: "succeeded" } },
        ]),
      }),
    );
    for (const visit of [() => page.goto(`/ideas/${idea.id}`), () => page.reload()]) {
      await visit();
      const notices = page.getByRole("list", { name: "Notices" });
      await expect(notices).toContainText("Research is skipped: Exa isn't set up.");
      await expect(notices.getByRole("link", { name: "Add an Exa key for a new run" })).toBeVisible();
      await page.getByRole("button", { name: /^Skipped 1 step/ }).click();
      await expect(page.getByRole("list", { name: "Steps" }).getByRole("listitem")).toHaveCount(1);
      await expect(page.getByRole("list", { name: "Steps" })).toContainText("(skipped)");
      await expect(page.getByText("Run finished.")).toBeVisible();
    }
  });
});
