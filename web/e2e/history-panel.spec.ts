import { expect, test, type Page, type Route } from "@playwright/test";

import { eventStreamBody, seedQueuedRun } from "./support/runs";
import { SESSION_COOKIE, createSessionToken } from "./support/session";

const LAPTOP = { width: 1440, height: 900 };
const PHONE = { width: 375, height: 800 };
const WORKSPACE_ID = "00000000-0000-7000-8000-0000000000aa";

type Stage = "intake" | "scoring" | "spec_draft" | "spec_confirmed";

interface FakeIdea {
  id: string;
  title: string;
  stage: Stage;
  currentScore: number | null;
  updatedAt: string;
  totals?: number[];
  band?: "build" | "promising" | "advise";
}

const NOW = Date.now();
const DAY_MS = 86_400_000;

function ideaId(n: number): string {
  return `00000000-0000-7000-8000-${String(n).padStart(12, "0")}`;
}

const IDEAS: FakeIdea[] = [
  { id: ideaId(1), title: "Pocket CRM", stage: "spec_draft", currentScore: 63, updatedAt: new Date(NOW - 60_000).toISOString(), totals: [54, 63], band: "promising" },
  { id: ideaId(2), title: "Garden planner", stage: "scoring", currentScore: 52, updatedAt: new Date(NOW - 3 * DAY_MS).toISOString(), totals: [56, 52], band: "advise" },
  { id: ideaId(3), title: "Habit tracker", stage: "spec_confirmed", currentScore: 76, updatedAt: new Date(NOW - 20 * DAY_MS).toISOString(), totals: [61, 70, 76], band: "build" },
  { id: ideaId(4), title: "Invoice chaser", stage: "intake", currentScore: null, updatedAt: new Date(NOW - 40 * DAY_MS).toISOString() },
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

/** Fakes the list and the summaries with the server's `q` / `filter` / cursor behavior. */
async function fakeHistory(page: Page, ideas: FakeIdea[] = IDEAS, pageSize = ideas.length) {
  await page.route("**/v1/ideas?**", async (route: Route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const filter = url.searchParams.get("filter") ?? "all";
    const start = Number(url.searchParams.get("cursor") ?? 0);
    const matching = ideas
      .filter((idea) => idea.title.toLowerCase().includes(q))
      .filter((idea) => filter !== "scored" || idea.currentScore !== null)
      .filter((idea) => filter !== "in_progress" || idea.stage !== "spec_confirmed");
    const items = matching.slice(start, start + pageSize).map(toApiIdea);
    const next = start + pageSize < matching.length ? String(start + pageSize) : null;
    await route.fulfill({ json: { items, next_cursor: next } });
  });
  await page.route("**/v1/scores/summaries?**", async (route: Route) => {
    const ids = (new URL(route.request().url()).searchParams.get("idea_ids") ?? "").split(",");
    const items = ideas
      .filter((idea) => ids.includes(idea.id) && idea.totals)
      .map((idea) => ({ idea_id: idea.id, band: idea.band, totals: idea.totals }));
    await route.fulfill({ json: { items } });
  });
}

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

const historyPanel = (page: Page) => page.getByRole("complementary", { name: "Ideas" });
const search = (page: Page) => page.getByRole("searchbox", { name: "Search ideas" });
const rowFor = (page: Page, title: string) => historyPanel(page).getByRole("link", { name: new RegExp(`^${title},`) });

async function openHistory(page: Page, size = LAPTOP, path = "/") {
  await page.setViewportSize(size);
  await page.goto(path);
  await expect(page.getByLabel("Your idea")).toBeVisible();
  await page.getByRole("button", { name: "Your ideas" }).click();
  await expect(historyPanel(page)).toHaveAttribute("data-open", "true");
}

test.describe("history panel", () => {
  test("lists ideas grouped by last activity, with score, stage and a trend", async ({ page }) => {
    await fakeHistory(page);

    await openHistory(page);

    await expect(historyPanel(page).getByRole("heading", { name: "Today" })).toBeVisible();
    await expect(historyPanel(page).getByRole("heading", { name: "This week" })).toBeVisible();
    await expect(historyPanel(page).getByRole("heading", { name: "Earlier" })).toBeVisible();
    await expect(rowFor(page, "Pocket CRM")).toContainText("63");
    await expect(rowFor(page, "Pocket CRM")).toContainText("Spec draft");
    await expect(rowFor(page, "Invoice chaser")).toContainText("–");
    await expect(historyPanel(page).getByRole("img", { name: "Score history v1 54 → v2 63" })).toBeVisible();
    await expect(historyPanel(page).getByRole("img", { name: /v1 61 → v2 70 → v3 76/ })).toBeVisible();
    await expect(rowFor(page, "Invoice chaser").getByRole("img")).toHaveCount(0);
    await expect(historyPanel(page)).toContainText("4 ideas");
    await expect(historyPanel(page)).toContainText("Sorted by last activity");
  });

  test("search and the filters work together, and an empty result says so", async ({ page }) => {
    await fakeHistory(page);
    await openHistory(page);

    await search(page).fill("pocket");
    await expect(rowFor(page, "Pocket CRM")).toBeVisible();
    await expect(rowFor(page, "Garden planner")).toHaveCount(0);

    await historyPanel(page).getByRole("button", { name: "Scored" }).click();
    await expect(rowFor(page, "Pocket CRM")).toBeVisible();

    await search(page).fill("invoice");
    await expect(historyPanel(page).getByText("No ideas match.")).toBeVisible();

    await search(page).fill("");
    await historyPanel(page).getByRole("button", { name: "In progress" }).click();
    await expect(rowFor(page, "Habit tracker")).toHaveCount(0);
    await expect(rowFor(page, "Invoice chaser")).toBeVisible();
  });

  test("/ opens the panel and focuses the search from anywhere", async ({ page }) => {
    await fakeHistory(page);
    await page.setViewportSize(LAPTOP);
    await page.goto("/");
    await expect(page.getByLabel("Your idea")).toBeVisible();
    await page.locator("body").click({ position: { x: 5, y: 5 } });

    await page.keyboard.press("/");

    await expect(historyPanel(page)).toHaveAttribute("data-open", "true");
    await expect(search(page)).toBeFocused();
  });

  test("the open idea is marked and clicking another row opens it", async ({ page }) => {
    await fakeHistory(page);
    await openHistory(page, LAPTOP, `/ideas/${ideaId(1)}`);

    await expect(rowFor(page, "Pocket CRM")).toHaveAttribute("aria-current", "page");
    await rowFor(page, "Garden planner").click();

    await page.waitForURL(`**/ideas/${ideaId(2)}`);
    await expect(rowFor(page, "Garden planner")).toHaveAttribute("aria-current", "page");
  });

  test("more ideas load as the list scrolls to its end", async ({ page }) => {
    const many: FakeIdea[] = Array.from({ length: 30 }, (_, n) => ({
      id: ideaId(100 + n),
      title: `Idea number ${n}`,
      stage: "intake",
      currentScore: null,
      updatedAt: new Date(NOW - n * 60_000).toISOString(),
    }));
    await fakeHistory(page, many, 12);
    await openHistory(page);
    await expect(historyPanel(page).getByRole("link")).toHaveCount(12);

    await historyPanel(page).getByRole("link").last().scrollIntoViewIfNeeded();

    await expect(historyPanel(page).getByRole("link", { name: /Idea number 29,/ })).toBeVisible({ timeout: 10_000 });
    await expect(historyPanel(page)).toContainText("30 ideas");
  });

  test("a row's menu deletes the idea after confirming", async ({ page }) => {
    await fakeHistory(page);
    let deleted: string | null = null;
    await page.route(`**/v1/ideas/${ideaId(4)}`, async (route) => {
      deleted = route.request().method() === "DELETE" ? ideaId(4) : null;
      await route.fulfill({ status: 204 });
    });
    await openHistory(page);

    await page.getByRole("button", { name: "Actions for Invoice chaser" }).click({ force: true });
    await page.getByRole("menuitem", { name: "Delete" }).click();
    await page.getByRole("button", { name: "Delete idea" }).click();

    await expect.poll(() => deleted).toBe(ideaId(4));
  });

  test("on a phone the overlay focuses the search and closes after picking an idea", async ({ page }) => {
    await fakeHistory(page);
    await openHistory(page, PHONE);
    await expect(search(page)).toBeFocused();

    await rowFor(page, "Garden planner").click();

    await page.waitForURL(`**/ideas/${ideaId(2)}`);
    await expect(historyPanel(page)).toHaveAttribute("data-open", "false");
    const noOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    );
    expect(noOverflow).toBe(true);
  });
});

test.describe("history panel while a run works", () => {
  async function createIdea(page: Page, label: string): Promise<{ id: string; workspace_id: string; title: string }> {
    const title = `E2E ${label} ${Date.now()}`;
    const response = await page.request.post("/v1/ideas", {
      headers: { "X-Metis-Client": "web" },
      data: { title, raw_text: `${title}\nA longer description of the idea for the test.` },
    });
    expect(response.status()).toBe(201);
    return { ...(await response.json()), title };
  }

  test("switching to another idea is blocked with a toast while a step is active", async ({ page, context }) => {
    await context.request.get("/v1/workspaces/current");
    const working = await createIdea(page, "working");
    const other = await createIdea(page, "other");
    const runId = seedQueuedRun(working.id, working.workspace_id);
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
    await openHistory(page, LAPTOP, `/ideas/${working.id}`);
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();

    await historyPanel(page).getByRole("link", { name: new RegExp(`^${other.title},`) }).click();

    await expect(page.getByText(/Metis is working on this idea/)).toBeVisible();
    expect(page.url()).toContain(`/ideas/${working.id}`);
  });
});
