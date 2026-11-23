import { expect, test, type Page, type Route } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { eventStreamBody, seedQueuedRun } from "./support/runs";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };
const PARAMS = ["problem_severity", "uniqueness", "market_demand", "value", "feasibility", "timing"] as const;
const WEIGHTS = [25, 25, 15, 15, 10, 10];
const SCORE_ID = "00000000-0000-4000-8000-0000000000c2";
const OLD_SCORE_ID = "00000000-0000-4000-8000-0000000000c1";
const SUGGESTION_ID = "00000000-0000-4000-8000-0000000000d1";
/** The faked event stream arrives this long after the page loaded, so the first load sees no score. */
const LIVE_DELAY_MS = 1500;

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function scoreRun(id: string, total: number, raw: number, createdAt: string) {
  return {
    id,
    idea_id: "x",
    run_id: "x",
    rubric_version: 1,
    trigger: "manual",
    total,
    band: "promising",
    created_at: createdAt,
    weights: {},
    params: PARAMS.map((param, index) => ({
      param,
      weight: WEIGHTS[index],
      raw,
      weighted: (raw * WEIGHTS[index]!) / 10,
      reason: `Reason for ${param}`,
      confidence: 0.8,
      no_evidence: false,
      evidence: [{ url: `https://example.com/${param}`, title: `Source ${param}`, quote: `Quote ${param}` }],
    })),
  };
}

const NEW_SCORE = scoreRun(SCORE_ID, 63, 6, "2026-11-21T10:00:00Z");
const OLD_SCORE = scoreRun(OLD_SCORE_ID, 56, 5, "2026-11-20T10:00:00Z");

function suggestion(status: string) {
  return {
    id: SUGGESTION_ID,
    idea_id: "x",
    score_run_id: OLD_SCORE_ID,
    kind: "niche",
    title: "Narrow to freelancers",
    rationale: "Incumbents ignore this group.",
    target_params: ["uniqueness"],
    expected_impact: "+6 on uniqueness",
    evidence: [],
    status,
    created_at: "2026-11-20T10:00:00Z",
  };
}

interface FakeOptions {
  /** The score appears only after the page loaded (a live output) instead of being there at load. */
  live?: boolean;
}

/** An idea whose scores and suggestions are served from memory; the run's event stream is faked. */
async function fakeScoredIdea(page: Page, { live = false }: FakeOptions = {}) {
  const created = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title: `E2E panel ${Date.now()}`, raw_text: `E2E panel ${Date.now()}\nA longer description of the idea.` },
  });
  expect(created.status()).toBe(201);
  const idea = (await created.json()) as { id: string; workspace_id: string };
  const runId = seedQueuedRun(idea.id, idea.workspace_id);
  const state = { scored: !live };

  await page.route(`**/v1/runs/${runId}/events**`, async (route) => {
    if (live) {
      await new Promise((resolve) => setTimeout(resolve, LIVE_DELAY_MS));
      state.scored = true;
    }
    const events = [
      { type: "score", data: { score_run_id: SCORE_ID, total: 63, band: "promising" } },
      { type: "run_status", data: { status: "succeeded" } },
    ];
    await route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: eventStreamBody(runId, events) });
  });
  await page.route(`**/v1/ideas/${idea.id}/interview`, (route) => fulfillJson(route, { items: [] }));
  await page.route(`**/v1/ideas/${idea.id}/scores/latest`, (route) =>
    state.scored
      ? fulfillJson(route, NEW_SCORE)
      : route.fulfill({
          status: 404,
          contentType: "application/problem+json",
          body: JSON.stringify({ title: "No score", code: "score.not_found", status: 404, detail: "No score", retryable: false, errors: [] }),
        }),
  );
  await page.route(`**/v1/ideas/${idea.id}/scores`, (route) =>
    fulfillJson(route, {
      items: [
        { ...NEW_SCORE, params: undefined, weights: undefined },
        { ...OLD_SCORE, params: undefined, weights: undefined },
      ],
    }),
  );
  await page.route(`**/v1/scores/${OLD_SCORE_ID}`, (route) => fulfillJson(route, OLD_SCORE));
  await page.route(`**/v1/scores/${SCORE_ID}`, (route) => fulfillJson(route, NEW_SCORE));
  const suggestionStatus = { value: "accepted" };
  await page.route(`**/v1/ideas/${idea.id}/suggestions`, (route) =>
    fulfillJson(route, { items: state.scored ? [suggestion(suggestionStatus.value)] : [] }),
  );
  return idea;
}

const outputPanel = (page: Page) => page.getByRole("complementary", { name: "Output" });

test.describe("opening rules", () => {
  test("a score produced live opens the panel on Score without taking focus", async ({ page }) => {
    const idea = await fakeScoredIdea(page, { live: true });
    await page.goto(`/ideas/${idea.id}`);

    await expect(outputPanel(page)).toHaveAttribute("data-open", "true", { timeout: LIVE_DELAY_MS * 4 });
    await expect(outputPanel(page).getByRole("tab", { name: /^Score/ })).toHaveAttribute("aria-selected", "true");
    const focusInPanel = await page.evaluate(() => document.querySelector("#output-panel")?.contains(document.activeElement) ?? false);
    expect(focusInPanel).toBe(false);
  });

  test("Esc closes the auto-opened panel and leaves the toggle enabled", async ({ page }) => {
    const idea = await fakeScoredIdea(page, { live: true });
    await page.goto(`/ideas/${idea.id}`);
    await expect(outputPanel(page)).toHaveAttribute("data-open", "true", { timeout: LIVE_DELAY_MS * 4 });

    await page.keyboard.press("Escape");
    await expect(outputPanel(page)).toHaveAttribute("data-open", "false");
    await expect(page.getByRole("button", { name: "Open output" })).toBeEnabled();
  });

  test("an idea that already has a score loads with the panel closed", async ({ page }) => {
    const idea = await fakeScoredIdea(page);
    await page.goto(`/ideas/${idea.id}`);

    await expect(page.locator('[data-pane="score"]')).toBeVisible();
    await expect(outputPanel(page)).toHaveAttribute("data-open", "false");
  });

  test("on a phone nothing opens by itself", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    const idea = await fakeScoredIdea(page, { live: true });
    await page.goto(`/ideas/${idea.id}`);

    await expect(page.locator('[data-pane="score"]')).toBeVisible({ timeout: LIVE_DELAY_MS * 4 });
    await expect(outputPanel(page)).toHaveAttribute("data-open", "false");
  });
});

test.describe("tabs", () => {
  test("show counts, disable empty tabs and move with the arrow keys", async ({ page }) => {
    const idea = await fakeScoredIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="score"]').click();

    const panel = outputPanel(page);
    await expect(panel.getByRole("tab", { name: /^Score/ })).toContainText("2");
    await expect(panel.getByRole("tab", { name: /^Suggestions/ })).toContainText("1");
    await expect(panel.getByRole("tab", { name: /^Research/ })).toBeDisabled();
    await expect(panel.getByRole("tab", { name: /^Spec/ })).toBeDisabled();

    await panel.getByRole("tab", { name: /^Score/ }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(panel.getByRole("tab", { name: /^Suggestions/ })).toHaveAttribute("aria-selected", "true");
    await expect(panel.getByRole("tab", { name: /^Suggestions/ })).toBeFocused();
    await page.keyboard.press("Home");
    await expect(panel.getByRole("tab", { name: /^Score/ })).toHaveAttribute("aria-selected", "true");
  });

  test("Esc closes the panel", async ({ page }) => {
    const idea = await fakeScoredIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="score"]').click();
    await expect(outputPanel(page)).toHaveAttribute("data-open", "true");

    await page.keyboard.press("Escape");
    await expect(outputPanel(page)).toHaveAttribute("data-open", "false");
  });
});

test.describe("score pane", () => {
  test("shows the delta from the version before", async ({ page }) => {
    const idea = await fakeScoredIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="score"]').click();

    await expect(page.getByText("▲ 7 from v1")).toBeVisible();
    await expect(page.getByText("v2 · rescore")).toBeVisible();
  });

  test("the footer stays in view and exports a Markdown report", async ({ page }) => {
    const idea = await fakeScoredIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="score"]').click();

    await outputPanel(page).getByRole("button", { name: "Export" }).click();
    await expect(page.getByRole("menuitem", { name: /Linear/ })).toHaveAttribute("aria-disabled", "true");
    const download = page.waitForEvent("download");
    await page.getByRole("menuitem", { name: "Markdown report" }).click();
    expect((await download).suggestedFilename()).toMatch(/^metis-.*-score\.md$/);
  });
});

test.describe("suggestions pane", () => {
  test("shows impact, the Applied tag and the footer hint", async ({ page }) => {
    const idea = await fakeScoredIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="suggestions"]').click();

    const panel = outputPanel(page);
    await expect(panel.getByText("Narrow to freelancers")).toBeVisible();
    await expect(panel.getByText("+6 on uniqueness")).toBeVisible();
    await expect(panel.getByText("Applied in v2")).toBeVisible();
    await expect(panel.getByText("Pick an angle in the chat to rescore")).toBeVisible();
  });

  test("the chat holds only a card, never the report", async ({ page }) => {
    const idea = await fakeScoredIdea(page);
    await page.goto(`/ideas/${idea.id}`);

    await expect(page.locator('[data-pane="suggestions"]')).toBeVisible();
    await expect(page.getByText("Reason for uniqueness")).toHaveCount(0);
    await expect(page.getByText("Narrow to freelancers")).toHaveCount(0);
  });
});
