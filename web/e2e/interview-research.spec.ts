import { expect, test, type Page, type Route } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { eventStreamBody, seedAwaitingRun, seedQueuedRun } from "./support/runs";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };
const QUESTION = "Who pays for this?";

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

type Turn = { id: string; question: string; answer: string | null; source?: "asked" | "noted" };

async function createIdea(page: Page, label: string): Promise<{ id: string; workspace_id: string }> {
  const text = `E2E ${label} ${Date.now()}\nA longer description of the idea for the test.`;
  const response = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title: text.split("\n")[0], raw_text: text },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function fulfillProblem(
  route: Route,
  status: number,
  code: string,
  title: string,
  errors: { field: string; message: string }[] = [],
) {
  return route.fulfill({
    status,
    contentType: "application/problem+json",
    body: JSON.stringify({ title, code, status, detail: title, retryable: false, errors }),
  });
}

/** An idea with a seeded run whose event stream and interview turns are faked. */
async function fakeRun(
  page: Page,
  options: {
    events: Parameters<typeof eventStreamBody>[1];
    /** What a reconnect after the first stream gets (the server resumes after `Last-Event-ID`). */
    laterEvents?: Parameters<typeof eventStreamBody>[1];
    turns?: Turn[];
    awaiting?: Record<string, unknown>;
  },
) {
  const idea = await createIdea(page, "interview");
  const runId = seedQueuedRun(idea.id, idea.workspace_id);
  if (options.awaiting) seedAwaitingRun(runId, options.awaiting);
  let streamCalls = 0;
  await page.route(`**/v1/runs/${runId}/events**`, (route) => {
    streamCalls += 1;
    const events = streamCalls > 1 && options.laterEvents ? options.laterEvents : options.events;
    return route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: eventStreamBody(runId, events),
    });
  });
  const items = (options.turns ?? []).map((turn) => ({
    ...turn,
    idea_id: idea.id,
    run_id: runId,
    topic: "problem",
    source: turn.source ?? "asked",
  }));
  await page.route(`**/v1/ideas/${idea.id}/interview`, (route) => fulfillJson(route, { items }));
  return { idea, runId };
}

const ASK = [
  { type: "interrupt", data: { type: "question", question: QUESTION } },
  { type: "run_status", data: { status: "awaiting_user" } },
];

/** Captures the resume bodies and answers 202. */
async function captureResume(page: Page, runId: string): Promise<unknown[]> {
  const bodies: unknown[] = [];
  await page.route(`**/v1/runs/${runId}/resume`, (route) => {
    bodies.push(route.request().postDataJSON());
    return fulfillJson(route, { run_id: runId }, 202);
  });
  return bodies;
}

const composer = (page: Page) => page.getByLabel("Reply to Metis");

test.describe("interview in the chat", () => {
  test("shows the question, sends the answer and waits for the agent", async ({ page }) => {
    const { idea, runId } = await fakeRun(page, { events: ASK });
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);

    await expect(page.getByText(QUESTION)).toBeVisible();
    await expect(composer(page)).toBeEnabled();
    await expect(composer(page)).toHaveAttribute("placeholder", "Type your answer");

    await composer(page).fill("Freelancers");
    await composer(page).press("Enter");

    await expect.poll(() => bodies).toEqual([{ value: "Freelancers" }]);
    await expect(page.getByText("Freelancers", { exact: true })).toBeVisible();
    // The run is about to move on: the dock shows the working bar, not the composer.
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
    await expect(composer(page)).toHaveCount(0);
  });

  test("Shift+Enter adds a line and sends nothing", async ({ page }) => {
    const { idea, runId } = await fakeRun(page, { events: ASK });
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);

    await composer(page).fill("first");
    await composer(page).press("Shift+Enter");
    await composer(page).pressSequentially("second");

    await expect(composer(page)).toHaveValue("first\nsecond");
    expect(bodies).toEqual([]);
  });

  test("an empty answer is blocked before sending", async ({ page }) => {
    const { idea, runId } = await fakeRun(page, { events: ASK });
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);

    await composer(page).fill("   ");
    await composer(page).press("Enter");

    expect(bodies).toEqual([]);
    await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  test("quick replies send Skip and That's enough at once", async ({ page }) => {
    const { idea, runId } = await fakeRun(page, { events: ASK });
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);

    await page.getByRole("button", { name: "Skip" }).click();
    await expect.poll(() => bodies).toEqual([{ value: "skip" }]);

    const second = await fakeRun(page, { events: ASK });
    const secondBodies = await captureResume(page, second.runId);
    await page.goto(`/ideas/${second.idea.id}`);
    await page.getByRole("button", { name: "That's enough" }).click();
    await expect.poll(() => secondBodies).toEqual([{ value: "that's enough" }]);
  });

  test("a 409 takes the answer back and says the run moved on", async ({ page }) => {
    const { idea, runId } = await fakeRun(page, { events: ASK });
    await page.route(`**/v1/runs/${runId}/resume`, (route) =>
      fulfillProblem(route, 409, "run.invalid_state", "The run is not waiting for an answer."),
    );
    await page.goto(`/ideas/${idea.id}`);

    await composer(page).fill("Freelancers");
    await composer(page).press("Enter");

    await expect(page.getByText("This run already moved on.")).toBeVisible();
    await expect(page.getByText("Freelancers", { exact: true })).toHaveCount(0);
    await expect(composer(page)).toHaveValue("Freelancers");
  });

  test("a failed resume removes the optimistic answer and shows the error", async ({ page }) => {
    const { idea, runId } = await fakeRun(page, { events: ASK });
    await page.route(`**/v1/runs/${runId}/resume`, (route) =>
      fulfillProblem(route, 422, "common.validation_failed", "Invalid resume value", [
        { field: "body.value", message: "That answer is not valid." },
      ]),
    );
    await page.goto(`/ideas/${idea.id}`);

    await composer(page).fill("Freelancers");
    await composer(page).press("Enter");

    await expect(page.getByRole("alert").filter({ hasText: "That answer is not valid." })).toBeVisible();
    await expect(page.getByText("Freelancers", { exact: true })).toHaveCount(0);
    await expect(composer(page)).toHaveValue("Freelancers");
  });

  test("a reload restores earlier answers and the pending question", async ({ page }) => {
    const turns: Turn[] = [
      { id: "t1", question: "Who feels the pain?", answer: "Freelancers" },
      { id: "t2", question: QUESTION, answer: null },
    ];
    const { idea } = await fakeRun(page, {
      events: ASK,
      turns,
      awaiting: { type: "question", question: QUESTION },
    });

    await page.goto(`/ideas/${idea.id}`);
    await page.reload();

    await expect(page.getByText("Who feels the pain?")).toBeVisible();
    await expect(page.getByText("Freelancers", { exact: true })).toBeVisible();
    await expect(page.getByText(QUESTION)).toHaveCount(1);
    await expect(composer(page)).toBeEnabled();
  });

  test("a repeated question is asked again, not shown as answered", async ({ page }) => {
    const turns: Turn[] = [
      { id: "t1", question: QUESTION, answer: "Agencies" },
      { id: "t2", question: QUESTION, answer: null },
    ];
    const { idea, runId } = await fakeRun(page, {
      events: ASK,
      turns,
      awaiting: { type: "question", question: QUESTION },
    });
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);

    await expect(page.getByText(QUESTION)).toHaveCount(2);
    await expect(page.getByText("Agencies", { exact: true })).toBeVisible();
    await expect(composer(page)).toBeEnabled();
    await composer(page).fill("Freelancers");
    await composer(page).press("Enter");
    await expect.poll(() => bodies).toEqual([{ value: "Freelancers" }]);
    await expect(page.getByText("Freelancers", { exact: true })).toBeVisible();
  });

  test("a second approval in the same run shows its own prompt", async ({ page }) => {
    const approval = (action: string) => [
      { type: "interrupt", data: { type: "approval", action, details: "" } },
      { type: "run_status", data: { status: "awaiting_user" } },
    ];
    const { idea, runId } = await fakeRun(page, {
      events: approval("Export to Linear"),
      laterEvents: approval("Export to Notion"),
    });
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);

    await page.getByRole("button", { name: "Approve" }).click();
    await expect.poll(() => bodies).toEqual([{ value: true }]);
    await expect(page.getByText("Export to Notion")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Approve" })).toBeEnabled();
    await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  });

  test("noted turns are not shown", async ({ page }) => {
    const { idea } = await fakeRun(page, {
      events: [{ type: "run_status", data: { status: "succeeded" } }],
      turns: [{ id: "t1", question: "Who is it for?", answer: "Freelancers", source: "noted" }],
    });
    await page.goto(`/ideas/${idea.id}`);
    await expect(page.getByText("Run finished.")).toBeVisible();
    await expect(page.getByText("Who is it for?")).toHaveCount(0);
  });

  test("approve and reject resume with a boolean", async ({ page }) => {
    const approval = [
      { type: "interrupt", data: { type: "approval", action: "Export to Linear", details: "12 issues" } },
      { type: "run_status", data: { status: "awaiting_user" } },
    ];
    for (const [label, expected] of [["Approve", true], ["Reject", false]] as const) {
      const { idea, runId } = await fakeRun(page, { events: approval });
      const bodies = await captureResume(page, runId);
      await page.goto(`/ideas/${idea.id}`);

      await expect(page.getByText("Export to Linear")).toBeVisible();
      await expect(page.getByText("12 issues")).toBeVisible();
      await page.getByRole("button", { name: label }).click();

      await expect.poll(() => bodies).toEqual([{ value: expected }]);
      await expect(page.getByText(expected ? "Approved" : "Rejected", { exact: true })).toBeVisible();
    }
  });
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
    { id: "f1", kind: "market_fact", title: "Market size", url: "https://news.example.org/crm-report", published_at: "2026-11-02", quote: "The freelancer CRM market grew 20%.", claim: "Freelancer CRM demand is growing.", confidence: 0.8 },
    { id: "f2", kind: "risk", title: "Churn", url: null, published_at: null, quote: null, claim: "High churn among solo users.", confidence: 0.5 },
  ],
};

const RESEARCH_DONE = [
  { type: "node_started", data: { node: "researcher" } },
  { type: "tool_call", data: { node: "researcher", name: "web_search_exa" } },
  { type: "node_finished", data: { node: "researcher" } },
  { type: "run_status", data: { status: "succeeded" } },
];

test.describe("research view", () => {
  test("shows Researching with the tool name while the Researcher works", async ({ page }) => {
    const { idea } = await fakeRun(page, {
      events: [
        { type: "node_started", data: { node: "researcher" } },
        { type: "tool_call", data: { node: "researcher", name: "web_search_exa" } },
        { type: "run_status", data: { status: "running" } },
      ],
    });
    await page.route(`**/v1/ideas/${idea.id}/research`, (route) =>
      fulfillProblem(route, 404, "research.not_found", "No research yet"),
    );
    await page.goto(`/ideas/${idea.id}`);
    await expect(page.getByText("Researching… Web search")).toBeVisible();
    await expect(page.getByText("Research", { exact: true })).toHaveCount(0);
  });

  test("the research reloads when the run ends, even without a finished Researcher step", async ({ page }) => {
    const { idea } = await fakeRun(page, {
      events: [
        { type: "node_started", data: { node: "researcher" } },
        { type: "run_status", data: { status: "succeeded" } },
      ],
    });
    let calls = 0;
    await page.route(`**/v1/ideas/${idea.id}/research`, (route) => {
      calls += 1;
      return calls === 1 ? fulfillProblem(route, 404, "research.not_found", "No research yet") : fulfillJson(route, RESEARCH);
    });
    await page.goto(`/ideas/${idea.id}`);
    await expect(page.locator('[data-pane="research"]')).toContainText("3 sources · 2 competitors");
  });

  test("a failed research load shows an error with Retry", async ({ page }) => {
    const { idea } = await fakeRun(page, { events: RESEARCH_DONE });
    let failing = true;
    await page.route(`**/v1/ideas/${idea.id}/research`, (route) =>
      failing ? fulfillProblem(route, 500, "common.unexpected", "Boom") : fulfillJson(route, RESEARCH),
    );
    await page.goto(`/ideas/${idea.id}`);

    await expect(page.getByText("Could not load the research.")).toBeVisible();
    failing = false;
    await page.getByRole("button", { name: "Retry" }).click();
    await expect(page.locator('[data-pane="research"]')).toContainText("3 sources · 2 competitors");
  });

  test("fits a phone screen with no horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    const { idea } = await fakeRun(page, { events: RESEARCH_DONE });
    await page.route(`**/v1/ideas/${idea.id}/research`, (route) => fulfillJson(route, RESEARCH));
    await page.goto(`/ideas/${idea.id}`);
    await page.locator('[data-pane="research"]').click();

    await expect(page.getByRole("region", { name: "Competitors" })).toContainText("Acme CRM");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
