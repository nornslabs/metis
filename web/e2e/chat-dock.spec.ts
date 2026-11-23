import { expect, test, type Page, type Route } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { eventStreamBody, seedAwaitingRun, seedQueuedRun } from "./support/runs";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };
const QUESTION = "Who is it for?";

const OPTIONS = [
  { id: "o1", label: "Solo freelancers", detail: "One person, no team.", recommended: true },
  { id: "o2", label: "Small agencies", recommended: false },
  { id: "o3", label: "In-house teams", recommended: false },
];

const SINGLE = {
  type: "question",
  question: QUESTION,
  multi: false,
  options: OPTIONS,
  allow_free_text: true,
  index: 2,
  total: 5,
};
const MULTI = {
  ...SINGLE,
  multi: true,
  options: [
    { id: "o1", label: "Solo freelancers", recommended: true },
    { id: "o2", label: "Small agencies", recommended: false },
    { id: "o3", label: "In-house teams", recommended: true },
  ],
};

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function createIdea(page: Page): Promise<{ id: string; workspace_id: string }> {
  const text = `E2E dock ${Date.now()}\nA longer description of the idea for the dock test.`;
  const response = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title: text.split("\n")[0], raw_text: text },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

/** An idea with a seeded run whose event stream is faked; `awaiting` also seeds the pending question. */
async function fakeRun(page: Page, events: Parameters<typeof eventStreamBody>[1], awaiting?: Record<string, unknown>) {
  const idea = await createIdea(page);
  const runId = seedQueuedRun(idea.id, idea.workspace_id);
  if (awaiting) seedAwaitingRun(runId, awaiting);
  await page.route(`**/v1/runs/${runId}/events**`, (route) =>
    route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: eventStreamBody(runId, events),
    }),
  );
  await page.route(`**/v1/ideas/${idea.id}/interview`, (route) => fulfillJson(route, { items: [] }));
  return { idea, runId };
}

const ask = (payload: Record<string, unknown>) => [
  { type: "interrupt", data: payload },
  { type: "run_status", data: { status: "awaiting_user" } },
];

async function captureResume(page: Page, runId: string): Promise<unknown[]> {
  const bodies: unknown[] = [];
  await page.route(`**/v1/runs/${runId}/resume`, (route) => {
    bodies.push(route.request().postDataJSON());
    return fulfillJson(route, { run_id: runId }, 202);
  });
  return bodies;
}

const picker = (page: Page) => page.getByRole("group", { name: /^Question/ });
const composer = (page: Page) => page.getByLabel("Reply to Metis");
const dockMode = (page: Page) => page.locator("[data-dock-mode]").getAttribute("data-dock-mode");

test.describe("answer options in the dock", () => {
  test("a single choice shows progress, the best fit and sends on a key", async ({ page }) => {
    const { idea, runId } = await fakeRun(page, ask(SINGLE));
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);

    await expect(picker(page)).toBeVisible();
    await expect(picker(page).getByText("Question 2 of 5")).toBeVisible();
    await expect(picker(page).getByText("1–3 to pick")).toBeVisible();
    await expect(picker(page).getByText("Best fit")).toHaveCount(1);
    await expect(composer(page)).toHaveCount(0);

    await page.keyboard.press("2");

    await expect.poll(() => bodies).toEqual([{ value: { option_ids: ["o2"] } }]);
    const bubble = page.getByText("Small agencies", { exact: true });
    await expect(bubble).toBeVisible();
    await expect(page.getByLabel("Picked")).toBeVisible();
    // The run is about to move on: the working bar replaces the picker without a composer flash.
    await expect.poll(() => dockMode(page)).toBe("busy");
  });

  test("a click on an option sends it", async ({ page }) => {
    const { idea, runId } = await fakeRun(page, ask(SINGLE));
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);

    await picker(page).getByRole("button", { name: /In-house teams/ }).click();

    await expect.poll(() => bodies).toEqual([{ value: { option_ids: ["o3"] } }]);
  });

  test("a multi choice pre-checks the recommended options, toggles with keys and confirms with Enter", async ({ page }) => {
    const { idea, runId } = await fakeRun(page, ask(MULTI));
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);

    const boxes = picker(page).getByRole("checkbox");
    await expect(boxes).toHaveCount(3);
    await expect(boxes.nth(0)).toBeChecked();
    await expect(boxes.nth(1)).not.toBeChecked();
    await expect(boxes.nth(2)).toBeChecked();
    await expect(page.getByRole("button", { name: "Continue (2)" })).toBeVisible();

    await page.keyboard.press("2");
    await expect(page.getByRole("button", { name: "Continue (3)" })).toBeVisible();
    await page.keyboard.press("1");
    await expect(page.getByRole("button", { name: "Continue (2)" })).toBeVisible();
    expect(bodies).toEqual([]);

    await page.keyboard.press("Enter");

    await expect.poll(() => bodies).toEqual([{ value: { option_ids: ["o2", "o3"] } }]);
  });

  test("Clear empties a multi choice and Continue waits for a pick", async ({ page }) => {
    const { idea, runId } = await fakeRun(page, ask(MULTI));
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);

    await page.getByRole("button", { name: "Clear" }).click();

    await expect(page.getByRole("button", { name: "Continue (0)" })).toBeDisabled();
    await page.keyboard.press("Enter");
    expect(bodies).toEqual([]);
  });

  test("key 0 opens the composer with a back button, and typed text is sent as text", async ({ page }) => {
    const { idea, runId } = await fakeRun(page, ask(SINGLE));
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);

    await page.keyboard.press("0");
    await expect(composer(page)).toBeVisible();
    await expect(picker(page)).toHaveCount(0);

    // Number keys type into the field; they never pick an option.
    await composer(page).fill("");
    await composer(page).pressSequentially("1");
    await expect(composer(page)).toHaveValue("1");
    expect(bodies).toEqual([]);

    await page.getByRole("button", { name: "Back to options" }).click();
    await expect(picker(page)).toBeVisible();
    await page.keyboard.press("0");
    await composer(page).fill("Students");
    await composer(page).press("Enter");

    await expect.poll(() => bodies).toEqual([{ value: { option_ids: [], text: "Students" } }]);
    await expect(page.getByText("Students", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Picked")).toHaveCount(0);
  });

  test("a question that does not allow free text has no Something else row", async ({ page }) => {
    const { idea } = await fakeRun(page, ask({ ...SINGLE, allow_free_text: false }));
    await page.goto(`/ideas/${idea.id}`);

    await expect(picker(page)).toBeVisible();
    await expect(page.getByText("Something else, let me type it")).toHaveCount(0);
    await page.keyboard.press("0");
    await expect(composer(page)).toHaveCount(0);
  });

  test("a plain question keeps the composer, and a reload restores a pending question with options", async ({ page }) => {
    const plain = await fakeRun(page, ask({ type: "question", question: "Why now?" }));
    await page.goto(`/ideas/${plain.idea.id}`);
    await expect(composer(page)).toBeEnabled();
    await expect(picker(page)).toHaveCount(0);

    const { idea } = await fakeRun(page, [], SINGLE);
    await page.goto(`/ideas/${idea.id}`);
    await page.reload();
    await expect(picker(page).getByText("Question 2 of 5")).toBeVisible();
    await expect(picker(page).getByRole("button", { name: /Solo freelancers/ })).toBeVisible();
  });

  test("an unreadable question shows a note instead of crashing", async ({ page }) => {
    const { idea } = await fakeRun(page, ask({ type: "question", question: QUESTION, options: [{ label: "No id" }] }));
    await page.goto(`/ideas/${idea.id}`);

    await expect(page.getByText("Metis asked something this page could not read.")).toBeVisible();
    await expect(picker(page)).toHaveCount(0);
  });
});

test.describe("dock modes and the input band", () => {
  test("the dock is the working bar while the run works, with a step counter and Stop", async ({ page }) => {
    const { idea } = await fakeRun(page, [
      { type: "run_status", data: { status: "running" } },
      { type: "node_started", data: { node: "interviewer" } },
      { type: "node_finished", data: { node: "interviewer" } },
      { type: "node_started", data: { node: "researcher" } },
      { type: "tool_call", data: { node: "researcher", name: "web_search_exa" } },
    ]);
    await page.goto(`/ideas/${idea.id}`);

    await expect.poll(() => dockMode(page)).toBe("busy");
    await expect(page.getByText("Researching… Web search")).toBeVisible();
    await expect(page.getByText("2/2")).toBeVisible();
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
    await expect(composer(page)).toHaveCount(0);
  });

  test("the input band element is the dock in every mode, and its top edge is the dock's", async ({ page }) => {
    const { idea } = await fakeRun(page, ask(SINGLE));
    await page.goto(`/ideas/${idea.id}`);

    const topOf = (selector: string) =>
      page.evaluate((query) => document.querySelector(query)?.getBoundingClientRect().top ?? null, selector);
    await expect.poll(() => dockMode(page)).toBe("choice");
    expect(await topOf('[data-frame="band"]')).toBe(await topOf("[data-dock-mode]"));

    await page.keyboard.press("0");
    await expect.poll(() => dockMode(page)).toBe("text");
    expect(await topOf('[data-frame="band"]')).toBe(await topOf("[data-dock-mode]"));
    expect(await page.locator('[data-frame="band"]').count()).toBe(1);
  });

  test("a finished run brings the composer back", async ({ page }) => {
    const { idea } = await fakeRun(page, [{ type: "run_status", data: { status: "succeeded" } }]);
    await page.goto(`/ideas/${idea.id}`);

    await expect(page.getByText("Run finished.")).toBeVisible();
    await expect.poll(() => dockMode(page)).toBe("text");
  });

  test("the thread is anchored to the bottom: the last message sits right above the dock", async ({ page }) => {
    const { idea } = await fakeRun(page, ask(SINGLE));
    await page.goto(`/ideas/${idea.id}`);
    await expect(picker(page)).toBeVisible();

    const gap = await page.evaluate(() => {
      const log = document.querySelector("[role=log]")!.getBoundingClientRect();
      const dock = document.querySelector("[data-dock-mode]")!.getBoundingClientRect();
      return dock.top - log.bottom;
    });
    expect(gap).toBeLessThan(40);
  });
});

test.describe("outputs are cards, not inline reports", () => {
  const RESEARCH = {
    id: "s1",
    idea_id: "i1",
    run_id: "r1",
    summary: "A crowded but fragmented market.",
    closed_at: "2026-11-19T10:00:00Z",
    created_at: "2026-11-19T09:00:00Z",
    competitors: [
      { id: "c1", name: "Acme CRM", url: "https://www.acmecrm.com/pricing", domain: "acmecrm.com", description: "CRM for freelancers", pricing: "$12 / month", overlap: 0.62, updated_at: "2026-11-19T09:30:00Z" },
      { id: "c2", name: "Pocket Sales", url: "https://pocketsales.io", domain: "pocketsales.io", description: null, pricing: null, overlap: 0.4, updated_at: "2026-11-19T09:30:00Z" },
    ],
    items: [
      { id: "f1", kind: "market_fact", title: "Market size", url: "https://news.example.org/crm-report", published_at: "2026-11-02", quote: "The freelancer CRM market grew 20%.", claim: "Freelancer CRM demand is growing.", confidence: 0.8 },
      { id: "f2", kind: "risk", title: "Churn", url: null, published_at: null, quote: null, claim: "High churn among solo users.", confidence: 0.5 },
    ],
  };

  test("research is one card that opens the output panel and is outlined while open", async ({ page }) => {
    const { idea } = await fakeRun(page, [
      { type: "node_started", data: { node: "researcher" } },
      { type: "node_finished", data: { node: "researcher" } },
      { type: "run_status", data: { status: "succeeded" } },
    ]);
    await page.route(`**/v1/ideas/${idea.id}/research`, (route) => fulfillJson(route, RESEARCH));
    await page.goto(`/ideas/${idea.id}`);

    const card = page.locator('[data-pane="research"]');
    await expect(card).toBeVisible();
    await expect(card).toContainText("2 sources · 2 competitors");
    await expect(card).toHaveAttribute("aria-pressed", "false");
    // Nothing of the report is in the chat.
    await expect(page.getByRole("log", { name: "Conversation" }).getByText("A crowded but fragmented market.")).toHaveCount(0);

    await card.click();

    await expect(page).toHaveURL(/panel=research/);
    await expect(card).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("tabpanel").getByText("2 competitors · 1 fact")).toBeVisible();
  });

  test("finished work is one collapsible line", async ({ page }) => {
    const { idea } = await fakeRun(page, [
      { type: "node_started", data: { node: "interviewer" } },
      { type: "node_finished", data: { node: "interviewer" } },
      { type: "node_started", data: { node: "scorer" } },
      { type: "node_finished", data: { node: "scorer" } },
      { type: "run_status", data: { status: "succeeded" } },
    ]);
    await page.goto(`/ideas/${idea.id}`);

    const summary = page.getByRole("button", { name: "Worked through 2 steps" });
    await expect(summary).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByRole("list", { name: "Steps" })).toHaveCount(0);

    await summary.click();

    await expect(summary).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("list", { name: "Steps" }).getByRole("listitem")).toHaveCount(2);
  });
});

test.describe("on a phone", () => {
  test("the picker fits 375px with no horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    const { idea } = await fakeRun(page, ask(MULTI));
    await page.goto(`/ideas/${idea.id}`);

    await expect(picker(page)).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
