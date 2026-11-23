import { readFile } from "node:fs/promises";

import { expect, test, type Page, type Route } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { eventStreamBody, seedQueuedRun } from "./support/runs";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };
const PARAMS = ["problem_severity", "uniqueness", "market_demand", "value", "feasibility", "timing"] as const;
const WEIGHTS = [25, 25, 15, 15, 10, 10];
const SCORE_ID = "00000000-0000-4000-8000-0000000000c2";
const FACT_URL = "https://news.example.org/crm-report";
const OUTSIDE_URL = "https://outside.example.com/a";

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

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
    { id: "f1", kind: "market_fact", title: "Market size", url: FACT_URL, published_at: "2026-11-02", quote: "The freelancer CRM market grew 20%.", claim: "Freelancer CRM demand is growing.", confidence: 0.8 },
    { id: "f2", kind: "risk", title: "Churn", url: null, published_at: null, quote: null, claim: "High churn among solo users.", confidence: 0.5 },
  ],
};

/** The fact page is cited with a fragment (same page, number 3); the second URL is not in the research. */
const SCORE = {
  id: SCORE_ID,
  idea_id: "x",
  run_id: "x",
  rubric_version: 1,
  trigger: "manual",
  total: 63,
  band: "promising",
  created_at: "2026-11-21T10:00:00Z",
  weights: {},
  params: PARAMS.map((param, index) => {
    const url = param === "problem_severity" ? `${FACT_URL}#section` : param === "uniqueness" ? OUTSIDE_URL : null;
    return {
      param,
      weight: WEIGHTS[index],
      raw: 6,
      weighted: (6 * WEIGHTS[index]!) / 10,
      reason: `Reason for ${param}`,
      confidence: 0.8,
      no_evidence: url === null,
      evidence: url === null ? [] : [{ url, title: `Page for ${param}`, quote: "A quote" }],
    };
  }),
};

const RESEARCH_DONE = [
  { type: "node_started", data: { node: "researcher" } },
  { type: "node_finished", data: { node: "researcher" } },
  { type: "run_status", data: { status: "succeeded" } },
];

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function fakeResearchedIdea(page: Page, research: unknown = RESEARCH) {
  const created = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title: `E2E sources ${Date.now()}`, raw_text: `E2E sources ${Date.now()}\nA longer description of the idea.` },
  });
  expect(created.status()).toBe(201);
  const idea = (await created.json()) as { id: string; workspace_id: string };
  const runId = seedQueuedRun(idea.id, idea.workspace_id);
  await page.route(`**/v1/runs/${runId}/events**`, (route) =>
    route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: eventStreamBody(runId, RESEARCH_DONE) }),
  );
  await page.route(`**/v1/ideas/${idea.id}/interview`, (route) => fulfillJson(route, { items: [] }));
  await page.route(`**/v1/ideas/${idea.id}/research`, (route) => fulfillJson(route, research));
  await page.route(`**/v1/ideas/${idea.id}/scores/latest`, (route) => fulfillJson(route, SCORE));
  await page.route(`**/v1/ideas/${idea.id}/scores`, (route) =>
    fulfillJson(route, { items: [{ ...SCORE, params: undefined, weights: undefined }] }),
  );
  await page.route(`**/v1/scores/${SCORE_ID}`, (route) => fulfillJson(route, SCORE));
  await page.route(`**/v1/ideas/${idea.id}/suggestions`, (route) => fulfillJson(route, { items: [] }));
  return idea;
}

const outputPanel = (page: Page) => page.getByRole("complementary", { name: "Output" });

test.describe("Research pane", () => {
  test("lists competitors, facts and numbered sources; the tab counts every source", async ({ page }) => {
    const idea = await fakeResearchedIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="research"]').click();

    const panel = outputPanel(page);
    // Three research sources plus the one the Scorer found outside the research.
    await expect(panel.getByRole("tab", { name: /^Research/ })).toContainText("4");
    await expect(panel.getByRole("region", { name: "Competitors" })).toContainText("Acme CRM");
    await expect(panel.getByRole("region", { name: "Market facts" })).toContainText("Freelancer CRM demand is growing.");
    await expect(panel.getByText("High churn among solo users.")).toBeVisible();

    const sources = panel.getByRole("list", { name: "Sources" }).getByTestId("source-row");
    await expect(sources).toHaveCount(4);
    await expect(sources.nth(0)).toContainText("Acme CRM");
    await expect(sources.nth(2)).toContainText("Market size");
    await expect(sources.nth(3)).toContainText("outside.example.com");
    await expect(panel.getByText("4 sources via Exa")).toBeVisible();
  });

  test("tags a competitor Direct from 50% overlap and Adjacent below", async ({ page }) => {
    const idea = await fakeResearchedIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="research"]').click();

    const competitors = outputPanel(page).getByRole("region", { name: "Competitors" });
    await expect(competitors.getByRole("listitem").filter({ hasText: "Acme CRM" })).toContainText("Direct");
    await expect(competitors.getByRole("listitem").filter({ hasText: "Pocket Sales" })).toContainText("Adjacent");
  });

  test("a chip on a competitor lands on its source row and flashes it", async ({ page }) => {
    const idea = await fakeResearchedIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="research"]').click();

    const panel = outputPanel(page);
    await panel.getByRole("region", { name: "Competitors" }).getByRole("button", { name: "Source 2: pocketsales.io" }).click();
    const row = panel.locator("#src-2");
    await expect(row).toHaveAttribute("data-flash", "true");
    await expect(row).toBeInViewport();
    await expect(row.getByRole("link", { name: "Open pocketsales.io" })).toBeFocused();
    await expect(row).not.toHaveAttribute("data-flash", "true", { timeout: 4000 });
  });

  test("a chip on a rubric reason opens Research on the right source, including one outside the research", async ({ page }) => {
    const idea = await fakeResearchedIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="score"]').click();

    const panel = outputPanel(page);
    await panel.getByRole("button", { name: /^Problem severity:/ }).click();
    // The fragment does not matter: it is the research's fact page, number 3.
    await panel.getByRole("button", { name: "Source 3: news.example.org" }).click();
    await expect(panel.getByRole("tab", { name: /^Research/ })).toHaveAttribute("aria-selected", "true");
    await expect(panel.locator("#src-3")).toHaveAttribute("data-flash", "true");

    await panel.getByRole("tab", { name: /^Score/ }).click();
    await panel.getByRole("button", { name: /^Uniqueness:/ }).click();
    await panel.getByRole("button", { name: "Source 4: outside.example.com" }).click();
    await expect(panel.locator("#src-4")).toContainText("Page for uniqueness");
  });

  test("with reduced motion the row is marked but nothing animates", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    const idea = await fakeResearchedIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="research"]').click();

    const panel = outputPanel(page);
    await panel.getByRole("button", { name: "Source 1: acmecrm.com" }).first().click();
    const animation = await panel.locator("#src-1").evaluate((element) => getComputedStyle(element).animationName);
    expect(animation).toBe("none");
  });

  test("source links open in a new tab safely and an unsafe URL gets no link or chip", async ({ page }) => {
    const unsafe = {
      ...RESEARCH,
      competitors: [],
      items: [{ ...RESEARCH.items[0], url: "javascript:alert(1)" }, RESEARCH.items[0]],
    };
    const idea = await fakeResearchedIdea(page, unsafe);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="research"]').click();

    const panel = outputPanel(page);
    const link = panel.getByRole("link", { name: "Open news.example.org" });
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", /noopener/);
    await expect(page.locator('a[href^="javascript:"]')).toHaveCount(0);
    // Only the safe fact has a chip.
    await expect(panel.getByRole("region", { name: "Market facts" }).getByTestId("cite")).toHaveCount(1);
  });

  test("Export sources downloads the numbered list", async ({ page }) => {
    const idea = await fakeResearchedIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="research"]').click();

    const downloading = page.waitForEvent("download");
    await outputPanel(page).getByRole("button", { name: "Export sources" }).click();
    const download = await downloading;
    expect(download.suggestedFilename()).toMatch(/^metis-e2e-sources-.*-sources\.md$/);
    const text = await readFile((await download.path())!, "utf8");
    expect(text).toContain("1. [Acme CRM](<https://www.acmecrm.com/pricing>) — acmecrm.com");
    expect(text).toContain("4. [Page for uniqueness](<https://outside.example.com/a>) — outside.example.com");
  });

  test("fits a phone screen with no horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    const idea = await fakeResearchedIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="research"]').click();

    await expect(outputPanel(page).getByText("Acme CRM").first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
