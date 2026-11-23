import { expect, test, type Page, type Route } from "@playwright/test";

import { removeSeededLlmKey, seedTestedLlmKey } from "./support/keys";
import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { eventStreamBody, seedAwaitingRun, seedQueuedRun } from "./support/runs";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };
const PARAMS = ["problem_severity", "uniqueness", "market_demand", "value", "feasibility", "timing"] as const;
const WEIGHTS = [25, 25, 15, 15, 10, 10];
const SCORE_ID = "00000000-0000-4000-8000-0000000000a1";
const OLD_SCORE_ID = "00000000-0000-4000-8000-0000000000a0";
const SUGGESTION_ID = "00000000-0000-4000-8000-0000000000b1";

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
  // The workspace exists after any API call; the refresh buttons are blocked without a tested LLM key.
  await context.request.get("/v1/workspaces/current");
  seedTestedLlmKey();
});

test.afterAll(() => removeSeededLlmKey());

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function fulfillProblem(route: Route, status: number, code: string, title: string) {
  return route.fulfill({
    status,
    contentType: "application/problem+json",
    body: JSON.stringify({ title, code, status, detail: title, retryable: false, errors: [] }),
  });
}

function scoreRun(id: string, total: number, band: string, raw: number, createdAt = new Date().toISOString()) {
  return {
    id,
    idea_id: "x",
    run_id: "x",
    rubric_version: 1,
    trigger: "manual",
    total,
    band,
    created_at: createdAt,
    weights: {},
    params: PARAMS.map((param, index) => ({
      param,
      weight: WEIGHTS[index],
      raw,
      weighted: (raw * WEIGHTS[index]!) / 10,
      reason: `Reason for ${param} (${total})`,
      confidence: param === "timing" ? 0.2 : 0.8,
      no_evidence: param === "timing",
      evidence:
        param === "timing"
          ? []
          : [{ url: `https://example.com/${param}`, title: `Source ${param}`, quote: `Quote ${param}` }],
    })),
  };
}

function suggestion(status: string) {
  return {
    id: SUGGESTION_ID,
    idea_id: "x",
    score_run_id: SCORE_ID,
    kind: "niche",
    title: "Narrow to freelancers",
    rationale: "Incumbents ignore this group.",
    target_params: ["uniqueness"],
    expected_impact: "Uniqueness 3 to 6",
    evidence: [{ url: "https://example.com/niche", title: "Niche", quote: "" }],
    status,
    created_at: new Date().toISOString(),
  };
}

type Options = {
  band?: string;
  total?: number;
  raw?: number;
  /** A pending advice decision for the run. */
  advice?: boolean;
  /** An active (waiting) run without an advice decision. */
  waiting?: boolean;
};

/** An idea whose run is faked and whose score, history and suggestions are served from memory. */
async function fakeScoredIdea(page: Page, options: Options = {}) {
  const { band = "advise", total = 48, raw = 4 } = options;
  const created = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title: `E2E score ${Date.now()}`, raw_text: `E2E score ${Date.now()}\nA longer description of the idea.` },
  });
  expect(created.status()).toBe(201);
  const idea = (await created.json()) as { id: string; workspace_id: string; raw_text: string };
  const runId = seedQueuedRun(idea.id, idea.workspace_id);
  const interrupt = options.advice
    ? { type: "advice_decision", score_run_id: SCORE_ID, total, band, suggestion_ids: [SUGGESTION_ID] }
    : options.waiting
      ? { type: "question", question: "Anything else?" }
      : null;
  if (interrupt) seedAwaitingRun(runId, interrupt);

  const events = [
    { type: "score", data: { score_run_id: SCORE_ID, total, band } },
    ...(interrupt ? [{ type: "interrupt", data: interrupt }, { type: "run_status", data: { status: "awaiting_user" } }] : [{ type: "run_status", data: { status: "succeeded" } }]),
  ];
  await page.route(`**/v1/runs/${runId}/events**`, (route) =>
    route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: eventStreamBody(runId, events) }),
  );
  await page.route(`**/v1/ideas/${idea.id}/interview`, (route) => fulfillJson(route, { items: [] }));

  const state = { suggestionStatus: "open", patches: [] as unknown[] };
  await page.route(`**/v1/ideas/${idea.id}/scores/latest`, (route) => fulfillJson(route, scoreRun(SCORE_ID, total, band, raw)));
  await page.route(`**/v1/ideas/${idea.id}/scores`, (route) =>
    fulfillJson(route, {
      items: [
        { ...scoreRun(SCORE_ID, total, band, raw), params: undefined, weights: undefined },
        { ...scoreRun(OLD_SCORE_ID, 40, "advise", 3, "2026-11-01T00:00:00Z"), params: undefined, weights: undefined },
      ],
    }),
  );
  await page.route(`**/v1/scores/${OLD_SCORE_ID}`, (route) => fulfillJson(route, scoreRun(OLD_SCORE_ID, 40, "advise", 3, "2026-11-01T00:00:00Z")));
  await page.route(`**/v1/scores/${SCORE_ID}`, (route) => fulfillJson(route, scoreRun(SCORE_ID, total, band, raw)));
  await page.route(`**/v1/ideas/${idea.id}/suggestions`, (route) => fulfillJson(route, { items: [suggestion(state.suggestionStatus)] }));
  await page.route(`**/v1/suggestions/${SUGGESTION_ID}`, (route) => {
    const body = route.request().postDataJSON() as { status: string };
    state.patches.push(body);
    state.suggestionStatus = body.status;
    return fulfillJson(route, suggestion(body.status));
  });
  return { idea, runId, state };
}

async function captureResume(page: Page, runId: string): Promise<unknown[]> {
  const bodies: unknown[] = [];
  await page.route(`**/v1/runs/${runId}/resume`, (route) => {
    bodies.push(route.request().postDataJSON());
    return fulfillJson(route, { run_id: runId }, 202);
  });
  return bodies;
}

test.describe("score card", () => {
  test("shows the total, band, last checked and six bars", async ({ page }) => {
    const { idea } = await fakeScoredIdea(page, { band: "promising", total: 62, raw: 6 });
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    const card = page.getByRole("region", { name: "Score" });
    await expect(card.getByText("62")).toBeVisible();
    await expect(card.getByText("Promising · 55–74")).toBeVisible();
    await expect(card.getByText("Last checked today")).toBeVisible();
    await expect(card.getByRole("button", { name: /out of 10/ })).toHaveCount(6);
  });

  test("a bar opens its reason, evidence and confidence; no evidence says so", async ({ page }) => {
    const { idea } = await fakeScoredIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    await page.getByRole("button", { name: /^Uniqueness: 4 out of 10/ }).click();
    await expect(page.getByText("Reason for uniqueness (48)")).toBeVisible();
    await expect(page.getByText("Confidence: High (0.80)")).toBeVisible();
    const link = page.getByRole("link", { name: /example\.com/ });
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", /noopener/);

    await page.getByRole("button", { name: /^Timing: 4 out of 10/ }).click();
    await expect(page.getByText("No evidence: this mark is a guess.")).toBeVisible();
    await expect(page.getByText("Confidence: Low (0.20)")).toBeVisible();
  });

  test("history lists both runs and compare shows signed deltas with reasons", async ({ page }) => {
    const { idea } = await fakeScoredIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    await expect(page.getByRole("button", { name: /^48 \/ 100 · Advise/ })).toBeVisible();
    const compare = page.getByRole("button", { name: "Compare" });
    await expect(compare).toBeDisabled();
    await page.getByRole("checkbox").nth(0).check();
    await page.getByRole("checkbox").nth(1).check();
    await compare.click();

    await expect(page.getByText("40 → 48 (+8)")).toBeVisible();
    await expect(page.getByText("3 → 4 (+1)").first()).toBeVisible();
    await expect(page.getByText("Before: Reason for uniqueness (40)")).toBeVisible();
    await expect(page.getByText("After: Reason for uniqueness (48)")).toBeVisible();
  });

  test("accept, undo and dismiss a suggestion; the choice survives a reload", async ({ page }) => {
    const { idea, state } = await fakeScoredIdea(page);
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    await expect(page.getByText("Narrow to freelancers")).toBeVisible();
    await page.getByRole("button", { name: "Accept" }).click();
    await expect(page.getByText("Accepted", { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByText("Accepted", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Undo" }).click();
    await page.getByRole("button", { name: "Dismiss" }).click();
    await expect(page.getByText("Dismissed", { exact: true })).toBeVisible();
    expect(state.patches).toEqual([{ status: "accepted" }, { status: "open" }, { status: "dismissed" }]);
  });
});

test.describe("advice decision", () => {
  test("continue and stop resume at once with the decision", async ({ page }) => {
    const { idea, runId } = await fakeScoredIdea(page, { advice: true });
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    await expect(page.getByRole("group", { name: "Decide what happens next" })).toBeVisible();
    await expect(page.getByLabel("Reply to Metis")).toHaveAttribute("placeholder", "Decide above");
    await page.getByRole("button", { name: "Continue to spec anyway" }).click();

    await expect.poll(() => bodies).toEqual([{ value: { decision: "continue", accepted_suggestion_ids: [] } }]);
    await expect(page.getByText("Continue to spec", { exact: true })).toBeVisible();
  });

  test("stop sends the stop decision", async ({ page }) => {
    const { idea, runId } = await fakeScoredIdea(page, { advice: true });
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    await page.getByRole("button", { name: "Stop here" }).click();
    await expect.poll(() => bodies).toEqual([{ value: { decision: "stop", accepted_suggestion_ids: [] } }]);
  });

  test("revise checks the length, then sends the text with the accepted suggestions", async ({ page }) => {
    const { idea, runId } = await fakeScoredIdea(page, { advice: true });
    const bodies = await captureResume(page, runId);
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    await page.getByRole("button", { name: "Accept" }).click();
    await page.getByRole("button", { name: "Revise idea and rescore" }).click();
    await expect(page.getByText("Narrow to freelancers").last()).toBeVisible();

    const editor = page.getByLabel("Revised idea");
    await editor.fill("too short");
    await page.getByRole("button", { name: "Send revision" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "at least 10" })).toBeVisible();
    expect(bodies).toEqual([]);

    await editor.fill("A revised idea aimed at freelancers who invoice late.");
    await page.getByRole("button", { name: "Send revision" }).click();
    await expect
      .poll(() => bodies)
      .toEqual([
        {
          value: {
            decision: "revise",
            revised_text: "A revised idea aimed at freelancers who invoice late.",
            accepted_suggestion_ids: [SUGGESTION_ID],
          },
        },
      ]);
    await expect(page.getByText("Revise and rescore", { exact: true })).toBeVisible();
  });

  test("a 409 says the run already moved on", async ({ page }) => {
    const { idea, runId } = await fakeScoredIdea(page, { advice: true });
    await page.route(`**/v1/runs/${runId}/resume`, (route) =>
      fulfillProblem(route, 409, "run.invalid_state", "The run is not waiting."),
    );
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    await page.getByRole("button", { name: "Stop here" }).click();
    await expect(page.getByText("This run already moved on.")).toBeVisible();
  });
});

test.describe("refresh actions", () => {
  test("Re-check market and Rescore start their runs with an idempotency key", async ({ page }) => {
    const { idea } = await fakeScoredIdea(page);
    const calls: { url: string; key: string | undefined }[] = [];
    await page.route(`**/v1/ideas/${idea.id}/recheck-market`, (route) => {
      calls.push({ url: route.request().url(), key: route.request().headers()["idempotency-key"] });
      return fulfillJson(route, { run_id: "00000000-0000-4000-8000-0000000000c1" }, 202);
    });
    await page.route(`**/v1/ideas/${idea.id}/rescore`, (route) => {
      calls.push({ url: route.request().url(), key: route.request().headers()["idempotency-key"] });
      return fulfillJson(route, { run_id: "00000000-0000-4000-8000-0000000000c2" }, 202);
    });
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    await page.getByRole("button", { name: "Re-check market" }).click();
    await expect.poll(() => calls.length).toBe(1);
    await page.getByRole("button", { name: "Rescore" }).click();
    await expect.poll(() => calls.length).toBe(2);
    expect(calls[0]?.url).toContain("/recheck-market");
    expect(calls[1]?.url).toContain("/rescore");
    expect(calls[0]?.key).toBeTruthy();
    expect(calls[0]?.key).not.toBe(calls[1]?.key);
  });

  test("a re-check with no research shows the instruction", async ({ page }) => {
    const { idea } = await fakeScoredIdea(page);
    await page.route(`**/v1/ideas/${idea.id}/recheck-market`, (route) =>
      fulfillProblem(route, 404, "research.not_found", "No research"),
    );
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    await page.getByRole("button", { name: "Re-check market" }).click();
    await expect(page.getByText("Run research first: there is no finished research to re-check.")).toBeVisible();
  });

  test("a 409 says a run is already in progress", async ({ page }) => {
    const { idea } = await fakeScoredIdea(page);
    await page.route(`**/v1/ideas/${idea.id}/rescore`, (route) =>
      fulfillProblem(route, 409, "run.already_running", "Already running"),
    );
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    await page.getByRole("button", { name: "Rescore" }).click();
    await expect(page.getByText("A run is already in progress for this idea.")).toBeVisible();
  });

  test("both buttons wait while a run is active", async ({ page }) => {
    const { idea } = await fakeScoredIdea(page, { waiting: true });
    await page.goto(`/ideas/${idea.id}`);
    // The score lives in the output panel; the chat holds one card that opens it.
    await page.locator('[data-pane="score"]').click();

    await expect(page.getByRole("button", { name: "Re-check market" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Rescore" })).toBeDisabled();
    await expect(page.getByText("Wait for the current run to finish.")).toBeVisible();
  });
});
