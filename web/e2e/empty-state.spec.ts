import { expect, test, type Page, type Route } from "@playwright/test";

import { eventStreamBody, seedQueuedRun } from "./support/runs";
import { SESSION_COOKIE, createSessionToken } from "./support/session";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };
const WORKSPACE_ID = "00000000-0000-7000-8000-0000000000aa";
const NOW = Date.now();
const DAY_MS = 86_400_000;
const BLINK_WAIT_MS = 6_000;

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

interface FakeIdea {
  id: string;
  title: string;
  stage: string;
  currentScore: number | null;
  updatedAt: string;
  totals?: number[];
  band?: "build" | "promising" | "advise";
}

function ideaId(n: number): string {
  return `00000000-0000-7000-8000-${String(n).padStart(12, "0")}`;
}

const IDEAS: FakeIdea[] = [
  { id: ideaId(1), title: "Pocket CRM", stage: "spec_draft", currentScore: 63, updatedAt: new Date(NOW - 60_000).toISOString(), totals: [54, 63], band: "promising" },
  { id: ideaId(2), title: "Garden planner", stage: "intake", currentScore: null, updatedAt: new Date(NOW - 3 * DAY_MS).toISOString() },
  { id: ideaId(3), title: "Habit tracker", stage: "spec_confirmed", currentScore: 76, updatedAt: new Date(NOW - 20 * DAY_MS).toISOString(), totals: [61, 76], band: "build" },
];

function toApiIdea(idea: FakeIdea) {
  return {
    id: idea.id,
    workspace_id: WORKSPACE_ID,
    created_by: WORKSPACE_ID,
    title: idea.title,
    raw_text: `${idea.title}: a longer description of the idea.`,
    kind: null,
    stage: idea.stage,
    current_score: idea.currentScore,
    version: 1,
    created_at: idea.updatedAt,
    updated_at: idea.updatedAt,
  };
}

async function fakeIdeas(page: Page, ideas: FakeIdea[]) {
  await page.route("**/v1/ideas?**", (route: Route) =>
    route.fulfill({ json: { items: ideas.map(toApiIdea), next_cursor: null } }),
  );
  await page.route("**/v1/scores/summaries?**", (route: Route) => {
    const ids = (new URL(route.request().url()).searchParams.get("idea_ids") ?? "").split(",");
    const items = ideas
      .filter((idea) => ids.includes(idea.id) && idea.totals)
      .map((idea) => ({ idea_id: idea.id, band: idea.band, totals: idea.totals }));
    return route.fulfill({ json: { items } });
  });
}

const recent = (page: Page) => page.getByRole("region", { name: "Recent ideas" });
const asciiOwl = (page: Page) => page.getByTestId("ascii-owl");

test.describe("empty state", () => {
  test("shows the two most recent ideas with stage, time and score", async ({ page }) => {
    await fakeIdeas(page, IDEAS);

    await page.goto("/");

    await expect(page.getByRole("heading", { name: "What are you building?" })).toBeVisible();
    await expect(recent(page).getByText("Pick up where you left off")).toBeVisible();
    const rows = recent(page).getByRole("link");
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0)).toHaveAccessibleName("Pocket CRM, score 63 Promising, Spec draft");
    await expect(rows.nth(0)).toContainText(/just now|\d+ min ago/);
    await expect(rows.nth(1)).toHaveAccessibleName("Garden planner, not scored, Intake");
    await expect(recent(page).getByText("Habit tracker")).toHaveCount(0);
  });

  test("a recent idea opens its conversation", async ({ page }) => {
    await fakeIdeas(page, IDEAS);
    await page.route(`**/v1/ideas/${ideaId(1)}**`, (route) => route.fulfill({ json: toApiIdea(IDEAS[0]!) }));
    await page.goto("/");

    await recent(page).getByRole("link", { name: /^Pocket CRM,/ }).click();

    await expect(page).toHaveURL(new RegExp(`/ideas/${ideaId(1)}$`));
  });

  test("All ideas opens the history panel", async ({ page }) => {
    await fakeIdeas(page, IDEAS);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");

    await recent(page).getByRole("button", { name: "All ideas" }).click();

    await expect(page.getByRole("complementary", { name: "Ideas" })).toHaveAttribute("data-open", "true");
  });

  test("has no recent box when the workspace has no ideas", async ({ page }) => {
    await fakeIdeas(page, []);

    await page.goto("/");

    await expect(page.getByLabel("Your idea")).toBeVisible();
    await expect(recent(page)).toHaveCount(0);
  });

  test("has no recent box and still works when the list fails", async ({ page }) => {
    await page.route("**/v1/ideas?**", (route) => route.fulfill({ status: 500, json: { title: "Boom" } }));

    await page.goto("/");

    await expect(page.getByLabel("Your idea")).toBeVisible();
    await expect(recent(page)).toHaveCount(0);
  });

  test("hides the hero owl on a short window", async ({ page }) => {
    await fakeIdeas(page, IDEAS);
    const heroOwl = page.getByTestId("hero-owl");

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await expect(heroOwl).toBeVisible();

    await page.setViewportSize({ width: 1440, height: 600 });
    await expect(heroOwl).toBeHidden();
  });

  test("does not draw the ASCII owl on the empty chat", async ({ page }) => {
    await fakeIdeas(page, IDEAS);

    await page.goto("/");

    await expect(page.getByLabel("Your idea")).toBeVisible();
    await expect(asciiOwl(page)).toHaveCount(0);
  });
});

async function workingIdea(page: Page): Promise<string> {
  const title = `E2E owl ${Date.now()}`;
  const response = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title, raw_text: `${title}\nA description long enough for the idea.` },
  });
  expect(response.status()).toBe(201);
  const idea: { id: string; workspace_id: string } = await response.json();
  const runId = seedQueuedRun(idea.id, idea.workspace_id);
  await page.route(`**/v1/ideas/${idea.id}/interview`, (route) => route.fulfill({ json: { items: [] } }));
  await page.route(`**/v1/runs/${runId}/events**`, (route) =>
    route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
      body: eventStreamBody(runId, [
        { type: "run_status", data: { status: "running" } },
        { type: "node_started", data: { node: "interviewer" } },
      ]),
    }),
  );
  return idea.id;
}

test.describe("ascii owl", () => {
  test("sits behind the conversation without catching the pointer", async ({ page }) => {
    const id = await workingIdea(page);

    await page.goto(`/ideas/${id}`);

    const layer = asciiOwl(page);
    await expect(layer).toBeAttached();
    await expect(layer).toHaveAttribute("aria-hidden", "true");
    await expect(layer).toHaveCSS("pointer-events", "none");
    await expect(layer.locator("pre")).toContainText("@");
    // Text in the thread stays reachable: the bubble is the topmost element at its centre.
    const bubble = page.getByText("A description long enough for the idea.").first();
    await expect(bubble).toBeVisible();
    const box = (await bubble.boundingBox())!;
    const topIsBubble = await page.evaluate(
      ([x, y]) => document.elementFromPoint(x!, y!)?.closest("[data-testid=ascii-owl]") === null,
      [box.x + box.width / 2, box.y + box.height / 2],
    );
    expect(topIsBubble).toBe(true);
  });

  test("closes its eyes now and then while Metis works", async ({ page }) => {
    const id = await workingIdea(page);
    await page.goto(`/ideas/${id}`);
    const pre = asciiOwl(page).locator("pre");
    await expect(pre).toHaveAttribute("data-eyes", "open");
    const open = await pre.textContent();

    await expect(pre).toHaveAttribute("data-eyes", "shut", { timeout: BLINK_WAIT_MS });

    expect(await pre.textContent()).not.toBe(open);
  });

  test("keeps its eyes open and does not fade under reduced motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    const id = await workingIdea(page);
    await page.goto(`/ideas/${id}`);
    const layer = asciiOwl(page);
    await expect(layer).toBeAttached();
    await expect(layer).toHaveCSS("animation-name", "none");

    // A negative check: wait past two blink beats, then the eyes must still be open.
    await page.waitForTimeout(BLINK_WAIT_MS);

    await expect(layer.locator("pre")).toHaveAttribute("data-eyes", "open");
  });
});
