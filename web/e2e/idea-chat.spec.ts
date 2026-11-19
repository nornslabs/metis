import { expect, test, type Page } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { removeSeededLlmKey, seedTestedLlmKey } from "./support/keys";
import { eventStreamBody, seedQueuedRun } from "./support/runs";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };
const RUN_TIMEOUT = 30_000;

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
  // A run can start only with a tested LLM key; the personal workspace is created by this call.
  await context.request.get("/v1/workspaces/current");
  seedTestedLlmKey();
});

test.afterAll(() => removeSeededLlmKey());

function uniqueIdea(label: string): string {
  return `E2E ${label} ${Date.now()}\nA longer description of the idea for the test.`;
}

/** Creates an idea through the API (no run) and returns its id and workspace. */
async function createIdea(page: Page, label: string): Promise<{ id: string; workspace_id: string }> {
  const text = uniqueIdea(label);
  const response = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title: text.split("\n")[0], raw_text: text },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

function steps(page: Page) {
  return page.getByRole("list", { name: "Steps" }).getByRole("listitem");
}

test.describe("idea chat", () => {
  test("sending an idea shows live steps, and a reload restores them without duplicates", async ({ page }) => {
    await page.goto("/");
    const text = uniqueIdea("live");
    await page.getByLabel("Your idea").fill(text);
    await page.getByLabel("Your idea").press("Enter");

    await page.waitForURL(/\/ideas\/[0-9a-f-]+$/);
    await expect(page.getByText(text.split("\n")[0])).toBeVisible();
    await expect(page.getByRole("log", { name: "Conversation" })).toHaveAttribute("aria-live", "polite");
    await expect(page.getByText("Run finished.")).toBeVisible({ timeout: RUN_TIMEOUT });
    await expect(steps(page).first()).toBeVisible();
    const count = await steps(page).count();
    expect(count).toBeGreaterThan(1);
    await expect(steps(page).filter({ hasText: "(running)" })).toHaveCount(0);

    await page.reload();
    await expect(page.getByText("Run finished.")).toBeVisible();
    await expect(steps(page)).toHaveCount(count);
  });

  test("blocks a too-short idea before sending", async ({ page }) => {
    let posted = false;
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().endsWith("/v1/ideas")) posted = true;
    });
    await page.goto("/");
    await page.getByLabel("Your idea").fill("too short");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText("Describe your idea in at least 10 characters.")).toBeVisible();
    expect(page.url()).not.toContain("/ideas/");
    expect(posted).toBe(false);
  });

  test("stop cancels an active run", async ({ page }) => {
    const idea = await createIdea(page, "cancel");
    const runId = seedQueuedRun(idea.id, idea.workspace_id);
    await page.goto(`/ideas/${idea.id}`);
    await page.getByRole("button", { name: "Stop" }).click();
    await expect(page.getByText("Run stopped.")).toBeVisible();
    const run = await (await page.request.get(`/v1/runs/${runId}`)).json();
    expect(run.status).toBe("cancelled");
  });

  test("a failed run shows its error and ignores bad frames; Retry reports a busy idea", async ({ page }) => {
    const idea = await createIdea(page, "failed");
    const runId = seedQueuedRun(idea.id, idea.workspace_id);
    await page.route(`**/v1/runs/${runId}/events**`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: eventStreamBody(runId, [
          { type: "run_status", data: { status: "running" } },
          { type: "node_started", data: { node: "interviewer" } },
          { type: "node_started", data: { wrong: "shape" } },
          { type: "score.param", data: { name: "market" } },
          "event: node_started\ndata: {not json\n\n",
          { type: "tool_call", data: { node: "interviewer", name: "ask_user" } },
          { type: "run_status", data: { status: "failed", error: { code: "run.failed", message: "Model call failed" } } },
        ]),
      }),
    );

    await page.goto(`/ideas/${idea.id}`);
    await expect(page.getByRole("alert").filter({ hasText: "Model call failed" })).toBeVisible();
    await expect(steps(page)).toHaveCount(1);
    await expect(steps(page).first()).toContainText("ask_user");

    // The seeded run is still queued on the server: the start is refused.
    await page.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByText("A run is already in progress for this idea.")).toBeVisible();

    const runs = await (await page.request.get(`/v1/ideas/${idea.id}/runs`)).json();
    expect(runs.items).toHaveLength(1);
    await page.request.post(`/v1/runs/${runId}/cancel`, { headers: MUTATION_HEADERS });
  });

  test("retry after a failure starts a new run", async ({ page }) => {
    const idea = await createIdea(page, "retry");
    const runId = seedQueuedRun(idea.id, idea.workspace_id);
    await page.route(`**/v1/runs/${runId}/events**`, async (route) => {
      // Free the idea first so the retry can start, then report the failure.
      await page.request.post(`/v1/runs/${runId}/cancel`, { headers: MUTATION_HEADERS });
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: eventStreamBody(runId, [
          { type: "run_status", data: { status: "failed", error: { code: "run.failed", message: "Boom" } } },
        ]),
      });
    });
    await page.goto(`/ideas/${idea.id}`);
    await page.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByText("Run finished.")).toBeVisible({ timeout: RUN_TIMEOUT });
    const runs = await (await page.request.get(`/v1/ideas/${idea.id}/runs`)).json();
    expect(runs.items).toHaveLength(2);
  });

  test("a run waiting on the user shows the question", async ({ page }) => {
    const idea = await createIdea(page, "interrupt");
    const runId = seedQueuedRun(idea.id, idea.workspace_id);
    await page.route(`**/v1/runs/${runId}/events**`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: eventStreamBody(runId, [
          { type: "interrupt", data: { type: "question", question: "Who pays for this?" } },
          { type: "run_status", data: { status: "awaiting_user" } },
        ]),
      }),
    );
    await page.goto(`/ideas/${idea.id}`);
    await expect(page.getByText("Who pays for this?")).toBeVisible();
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  });

  test("agent text is rendered as markdown without raw HTML", async ({ page }) => {
    const idea = await createIdea(page, "markdown");
    const runId = seedQueuedRun(idea.id, idea.workspace_id);
    await page.route(`**/v1/runs/${runId}/events**`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: eventStreamBody(runId, [
          { type: "token", data: { node: "advisor", text: "**Strong** demand <img src=x onerror=alert(1)>" } },
          { type: "run_status", data: { status: "succeeded" } },
        ]),
      }),
    );
    await page.goto(`/ideas/${idea.id}`);
    await expect(page.locator("strong", { hasText: "Strong" })).toBeVisible();
    await expect(page.locator("[role=log] img")).toHaveCount(0);
  });

  test("a server error frame stops the live view and says so", async ({ page }) => {
    const idea = await createIdea(page, "stream-error");
    const runId = seedQueuedRun(idea.id, idea.workspace_id);
    await page.route(`**/v1/runs/${runId}/events**`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: eventStreamBody(runId, [
          { type: "node_started", data: { node: "interviewer" } },
          'event: error\ndata: {"code":"run.event_malformed"}\n\n',
        ]),
      }),
    );
    await page.goto(`/ideas/${idea.id}`);
    await expect(page.getByText("Live updates stopped.", { exact: false })).toBeVisible();
    await expect(page.getByRole("button", { name: "Stop" })).toHaveCount(0);
    await page.request.post(`/v1/runs/${runId}/cancel`, { headers: MUTATION_HEADERS });
  });

  test("an unknown idea shows not found", async ({ page }) => {
    await page.goto("/ideas/00000000-0000-7000-8000-00000000dead");
    await expect(page.getByRole("heading", { name: "Idea not found" })).toBeVisible();
  });

  test("recent ideas lists the workspace's ideas and opens one", async ({ page }) => {
    const idea = await createIdea(page, "recent");
    await page.goto("/");
    await page.getByRole("button", { name: "Recent ideas" }).click();
    const item = page.getByRole("menuitem").filter({ hasText: "E2E recent" }).first();
    await expect(item).toBeVisible();
    await item.click();
    await page.waitForURL(`**/ideas/${idea.id}`);
  });

  test("the idea page has no horizontal scroll at 375px", async ({ page }) => {
    const idea = await createIdea(page, "mobile");
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto(`/ideas/${idea.id}`);
    await expect(page.getByRole("button", { name: "Start" })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
