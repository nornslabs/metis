import { expect, test, type Page, type Route } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { eventStreamBody, seedQueuedRun } from "./support/runs";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

const PHASES = [
  { name: "Foundations", goal: "Set up the repo", exit_criteria: "CI is green" },
  { name: "MVP", goal: "Ship the core", exit_criteria: "First users" },
];

type FakeTask = {
  id: string;
  position: number;
  title: string;
  description: string;
  estimate: number;
  labels: string[];
  parent_task_id: string | null;
  blocked_by: string[];
};

const fakeTask = (id: string, title: string, estimate: number, blockedBy: string[] = []): FakeTask => ({
  id,
  position: 0,
  title,
  description: `Description of ${title}`,
  estimate,
  labels: ["web"],
  parent_task_id: null,
  blocked_by: blockedBy,
});

interface FakePlanServer {
  version: number;
  status: "draft" | "ready";
  /** Plan requests answer `plan.not_found` until the run has been resumed. */
  exists: boolean;
  resumes: { phases: typeof PHASES }[];
  patches: { taskId: string; body: Record<string, unknown> }[];
  /** The next patch answers `plan.conflict`. */
  conflictNext: boolean;
  /** The next patch answers `plan.invalid_transition` after the plan became ready. */
  readyNext: boolean;
  /** The next resume answers 422 with a message. */
  resumeFails: boolean;
  tasks: FakeTask[][];
}

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function problem(code: string, status: number) {
  return { title: code, code, status, detail: code, retryable: false, errors: [] };
}

function planBody(ideaId: string, server: FakePlanServer) {
  const all = server.tasks.flat();
  // The critical path of the fake: t1 → t2 → t3.
  const points = ["t1", "t2", "t3"].reduce((sum, id) => sum + (all.find((entry) => entry.id === id)?.estimate ?? 0), 0);
  return {
    id: "plan1",
    idea_id: ideaId,
    spec_version_id: "sv1",
    status: server.status,
    version: server.version,
    ready_at: null,
    created_at: "2026-11-23T10:00:00Z",
    updated_at: "2026-11-23T10:00:00Z",
    phases: PHASES.map((phase, index) => ({
      id: `ph${index + 1}`,
      position: index,
      ...phase,
      tasks: (server.tasks[index] ?? []).map((entry, position) => ({ ...entry, position })),
    })),
    critical_path: { task_ids: ["t1", "t2", "t3"], points },
  };
}

async function fakePlanIdea(page: Page, options: { existing?: boolean; live?: boolean } = {}) {
  const created = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title: `E2E plan ${Date.now()}`, raw_text: `E2E plan ${Date.now()}\nA longer description of the idea.` },
  });
  expect(created.status()).toBe(201);
  const idea = (await created.json()) as { id: string; workspace_id: string };
  const runId = seedQueuedRun(idea.id, idea.workspace_id);
  const server: FakePlanServer = {
    version: 1,
    status: "draft",
    exists: options.existing === true,
    resumes: [],
    patches: [],
    conflictNext: false,
    readyNext: false,
    resumeFails: false,
    tasks: [
      [fakeTask("t1", "Set up CI", 2), fakeTask("t2", "Build the API", 5, ["t1"])],
      [fakeTask("t3", "Write the web app", 8, ["t2"]), fakeTask("t4", "Add sign-in", 3, ["t1"])],
    ],
  };

  const events: { type: string; data: unknown }[] = [{ type: "node_started", data: { node: "planner" } }];
  if (options.existing) events.push({ type: "run_status", data: { status: "succeeded" } });
  else {
    events.push({ type: "interrupt", data: { type: "phase_review", phases: PHASES } });
    events.push({ type: "run_status", data: { status: "awaiting_user" } });
  }
  // `live`: the Planner starts first and the review arrives on the stream's reconnect, like a real run.
  let deliveries = 0;
  await page.route(`**/v1/runs/${runId}/events**`, (route) => {
    deliveries += 1;
    const sent = options.live && deliveries === 1 ? events.slice(0, 1) : options.live ? events.slice(1) : events;
    return route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: eventStreamBody(runId, sent) });
  });
  await page.route(`**/v1/ideas/${idea.id}/interview`, (route) => fulfillJson(route, { items: [] }));
  await page.route(`**/v1/ideas/${idea.id}/research`, (route) => fulfillJson(route, problem("research.not_found", 404), 404));
  await page.route(`**/v1/ideas/${idea.id}/scores/latest`, (route) => fulfillJson(route, problem("score.not_found", 404), 404));
  await page.route(`**/v1/ideas/${idea.id}/scores`, (route) => fulfillJson(route, { items: [] }));
  await page.route(`**/v1/ideas/${idea.id}/suggestions`, (route) => fulfillJson(route, { items: [] }));
  await page.route(`**/v1/ideas/${idea.id}/spec`, (route) => fulfillJson(route, { latest: null, confirmed: null }));
  await page.route(`**/v1/ideas/${idea.id}/plan`, (route) =>
    server.exists ? fulfillJson(route, planBody(idea.id, server)) : fulfillJson(route, problem("plan.not_found", 404), 404),
  );
  await page.route(`**/v1/runs/${runId}/resume`, async (route) => {
    if (server.resumeFails) {
      server.resumeFails = false;
      return fulfillJson(route, { ...problem("run.invalid_resume", 422), detail: "The phases need a goal." }, 422);
    }
    const body = route.request().postDataJSON() as { value: { phases: typeof PHASES } };
    server.resumes.push(body.value);
    server.exists = true;
    return fulfillJson(route, { run_id: runId, status: "queued" }, 202);
  });
  await page.route(`**/v1/plans/plan1/tasks/*`, async (route) => {
    const taskId = route.request().url().split("/").at(-1) ?? "";
    const body = route.request().postDataJSON() as Record<string, unknown>;
    if (server.conflictNext) {
      server.conflictNext = false;
      server.version += 1;
      return fulfillJson(route, problem("plan.conflict", 409), 409);
    }
    if (server.readyNext) {
      server.readyNext = false;
      server.status = "ready";
      return fulfillJson(route, problem("plan.invalid_transition", 409), 409);
    }
    server.patches.push({ taskId, body });
    const target = server.tasks.flat().find((entry) => entry.id === taskId);
    if (target && typeof body.phase_id === "string") {
      const index = body.phase_id === "ph1" ? 0 : 1;
      server.tasks = server.tasks.map((list) => list.filter((entry) => entry.id !== taskId));
      server.tasks[index] = [...(server.tasks[index] ?? []), target];
    }
    if (target && typeof body.estimate === "number") target.estimate = body.estimate;
    if (target && typeof body.title === "string") target.title = body.title;
    server.version += 1;
    return fulfillJson(route, planBody(idea.id, server));
  });
  return { idea, server, runId };
}

const outputPanel = (page: Page) => page.getByRole("complementary", { name: "Output" });

async function openReview(page: Page) {
  const fake = await fakePlanIdea(page);
  await page.goto(`/ideas/${fake.idea.id}`);
  return fake;
}

async function openPlan(page: Page) {
  const fake = await fakePlanIdea(page, { existing: true });
  await page.goto(`/ideas/${fake.idea.id}?panel=plan`);
  return fake;
}

test.describe("Plan pane: phase review", () => {
  test("shows the proposed phases in the pane, with the chat prompt and card", async ({ page }) => {
    await openReview(page);
    const panel = outputPanel(page);
    await expect(page.getByRole("group", { name: "Review the phases" })).toBeVisible();
    await expect(page.locator('[data-pane="plan"]')).toContainText("Phases · 2");
    await page.locator('[data-pane="plan"]').click();
    await expect(panel.getByRole("textbox", { name: "P1 name" })).toHaveValue("Foundations");
    await expect(panel.getByRole("textbox", { name: "P2 Goal" })).toHaveValue("Ship the core");
    await expect(panel.getByText("2 phases")).toBeVisible();
  });

  test("edits change the footer note and Approve sends exactly the edited list", async ({ page }) => {
    const { server } = await openReview(page);
    await page.locator('[data-pane="plan"]').click();
    const panel = outputPanel(page);

    await panel.getByRole("textbox", { name: "P1 name" }).fill("Base");
    await panel.getByRole("button", { name: "Move P2 up" }).click();
    await expect(panel.getByText("2 phases · edited")).toBeVisible();
    await expect(panel.getByRole("textbox", { name: "P1 name" })).toHaveValue("MVP");

    await panel.getByRole("button", { name: "Approve phases" }).click();
    await expect.poll(() => server.resumes.length).toBe(1);
    expect(server.resumes[0]!.phases.map((phase) => phase.name)).toEqual(["MVP", "Base"]);
    await expect(panel.getByText("Planning tasks…")).toBeVisible();
  });

  test("approving the proposal untouched sends it back as it is", async ({ page }) => {
    const { server } = await openReview(page);
    await page.getByRole("group", { name: "Review the phases" }).getByRole("button", { name: "Approve phases" }).click();
    await expect.poll(() => server.resumes.length).toBe(1);
    expect(server.resumes[0]!.phases).toEqual(PHASES);
  });

  test("a phase without a goal blocks Approve and the last phase cannot be deleted", async ({ page }) => {
    await openReview(page);
    await page.locator('[data-pane="plan"]').click();
    const panel = outputPanel(page);
    await panel.getByRole("button", { name: "Add phase" }).click();
    await expect(panel.getByRole("button", { name: "Approve phases" })).toBeDisabled();
    await panel.getByRole("button", { name: "Delete P3" }).click();
    await panel.getByRole("button", { name: "Delete P2" }).click();
    await expect(panel.getByRole("button", { name: "Delete P1" })).toBeDisabled();
  });

  test("a refused phase list shows the server's message and keeps the edits", async ({ page }) => {
    const { server } = await openReview(page);
    await page.locator('[data-pane="plan"]').click();
    const panel = outputPanel(page);
    server.resumeFails = true;
    await panel.getByRole("textbox", { name: "P1 name" }).fill("Kept after refusal");
    await panel.getByRole("button", { name: "Approve phases" }).click();
    await expect(panel.getByRole("alert").filter({ hasText: "The phases need a goal." })).toBeVisible();
    await expect(panel.getByRole("textbox", { name: "P1 name" })).toHaveValue("Kept after refusal");
    await panel.getByRole("button", { name: "Approve phases" }).click();
    await expect.poll(() => server.resumes.length).toBe(1);
  });

  test("the panel opens on Plan once when the phases arrive live, and the card reopens it", async ({ page }) => {
    const fake = await fakePlanIdea(page, { live: true });
    await page.goto(`/ideas/${fake.idea.id}`);
    const panel = outputPanel(page);
    await expect(panel).toHaveAttribute("data-open", "true", { timeout: 15_000 });
    await expect(panel.getByRole("textbox", { name: "P1 name" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(panel).toHaveAttribute("data-open", "false");
    const card = page.locator('[data-pane="plan"]');
    await card.click();
    await expect(card).toHaveAttribute("aria-pressed", "true");
    await expect(panel.getByRole("textbox", { name: "P1 name" })).toBeVisible();
  });

  test("edits survive a reload before approving", async ({ page }) => {
    const { idea } = await openReview(page);
    await page.locator('[data-pane="plan"]').click();
    await outputPanel(page).getByRole("textbox", { name: "P1 name" }).fill("Kept");
    await page.goto(`/ideas/${idea.id}?panel=plan`);
    await expect(outputPanel(page).getByRole("textbox", { name: "P1 name" })).toHaveValue("Kept");
  });
});

test.describe("Plan pane: plan", () => {
  test("shows the summary, phase totals, blocker chips and the critical path", async ({ page }) => {
    await openPlan(page);
    const panel = outputPanel(page);
    await expect(panel.getByRole("tab", { name: /^Plan/ })).toContainText("4");
    await expect(panel.getByText("Critical path").first()).toBeVisible();
    await expect(panel.getByRole("region", { name: "P1 Foundations" })).toContainText("7 pts");
    await expect(panel.getByRole("region", { name: "P2 MVP" })).toContainText("11 pts");
    await expect(panel.getByRole("button", { name: "Blocked by T1: Set up CI" }).first()).toBeVisible();
    await expect(panel.locator('li[data-critical]')).toHaveCount(3);
    await expect(page.locator('[data-pane="plan"]')).toContainText("Plan · 4 tasks");
  });

  test("a plan present at load does not open the panel by itself", async ({ page }) => {
    const fake = await fakePlanIdea(page, { existing: true });
    await page.goto(`/ideas/${fake.idea.id}`);
    await expect(page.locator('[data-pane="plan"]')).toContainText("Plan · 4 tasks");
    await expect(outputPanel(page)).toHaveAttribute("data-open", "false");
  });

  test("an estimate change is saved once on the plan's version and totals follow", async ({ page }) => {
    const { server } = await openPlan(page);
    const panel = outputPanel(page);
    await panel.getByRole("button", { name: /^T2: Build the API/ }).click();
    await panel.getByRole("radiogroup", { name: "T2 estimate" }).getByRole("radio", { name: "8" }).click();

    await expect.poll(() => server.patches.length).toBe(1);
    expect(server.patches[0]).toEqual({ taskId: "t2", body: { version: 1, estimate: 8 } });
    await expect(panel.getByRole("region", { name: "P1 Foundations" })).toContainText("10 pts");
    await expect(panel.getByText("Saved · v2")).toBeVisible();
  });

  test("a title edit saves on blur and an empty title is refused", async ({ page }) => {
    const { server } = await openPlan(page);
    const panel = outputPanel(page);
    await panel.getByRole("button", { name: /^T1: Set up CI/ }).click();
    const title = panel.getByRole("textbox", { name: "T1 title" });
    await title.fill("");
    await title.blur();
    await expect(panel.getByText("A task needs a title.")).toBeVisible();
    expect(server.patches).toHaveLength(0);
    await title.fill("Set up CI and deploys");
    await title.blur();
    await expect.poll(() => server.patches.at(-1)?.body.title).toBe("Set up CI and deploys");
  });

  test("a stale version shows the notice and Reload shows the newest plan", async ({ page }) => {
    const { server } = await openPlan(page);
    const panel = outputPanel(page);
    server.conflictNext = true;
    await panel.getByRole("button", { name: /^T1: Set up CI/ }).click();
    await panel.getByRole("radiogroup", { name: "T1 estimate" }).getByRole("radio", { name: "3" }).click();
    await expect(panel.getByRole("alert").filter({ hasText: "Plan changed elsewhere" })).toBeVisible();
    await panel.getByRole("button", { name: "Reload" }).click();
    await expect(panel.getByRole("alert")).toHaveCount(0);
  });

  test("a ready plan is read-only", async ({ page }) => {
    const fake = await fakePlanIdea(page, { existing: true });
    fake.server.status = "ready";
    await page.goto(`/ideas/${fake.idea.id}?panel=plan`);
    const panel = outputPanel(page);
    await panel.getByRole("button", { name: /^T1: Set up CI/ }).click();
    await expect(panel.getByRole("textbox", { name: "T1 title" })).toHaveCount(0);
    await expect(panel.getByRole("radiogroup", { name: "T1 estimate" })).toHaveCount(0);
    await expect(panel.getByText("Plan ready · v1")).toBeVisible();
  });

  test("a blocker chip opens the task that blocks it", async ({ page }) => {
    await openPlan(page);
    const panel = outputPanel(page);
    await panel.getByRole("button", { name: "Blocked by T1: Set up CI" }).first().click();
    await expect(panel.getByRole("button", { name: /^T1: Set up CI/ })).toHaveAttribute("aria-expanded", "true");
  });

  test("moving a task to another phase saves the phase and keeps its blocker", async ({ page }) => {
    const { server } = await openPlan(page);
    const panel = outputPanel(page);
    await panel.getByRole("button", { name: /^T4: Add sign-in/ }).click();
    await panel.getByRole("combobox", { name: "T4 phase" }).selectOption("ph1");
    await expect.poll(() => server.patches.at(-1)?.body).toEqual({ version: 1, phase_id: "ph1" });
    await expect(panel.getByRole("region", { name: "P1 Foundations" })).toContainText("Add sign-in");
    await expect(panel.getByRole("region", { name: "P1 Foundations" }).getByRole("button", { name: "Blocked by T1: Set up CI" })).toBeVisible();
  });

  test("a plan fixed elsewhere locks the pane when a save is refused", async ({ page }) => {
    const { server } = await openPlan(page);
    const panel = outputPanel(page);
    server.readyNext = true;
    await panel.getByRole("button", { name: /^T1: Set up CI/ }).click();
    await panel.getByRole("radiogroup", { name: "T1 estimate" }).getByRole("radio", { name: "3" }).click();
    await expect(panel.getByText("Plan ready · v1")).toBeVisible();
    await expect(panel.getByRole("radiogroup", { name: "T1 estimate" })).toHaveCount(0);
  });

  test("the graph has a node per task and an edge per blocker, and Enter opens the task", async ({ page }) => {
    await openPlan(page);
    const panel = outputPanel(page);
    await panel.getByRole("button", { name: "graph" }).click();
    await expect(panel.locator("[data-node]")).toHaveCount(4);
    await expect(panel.locator("[data-edge]")).toHaveCount(3);
    await expect(panel.locator("[data-node][data-critical]")).toHaveCount(3);

    await panel.locator('[data-node="T3"]').focus();
    await page.keyboard.press("Enter");
    await expect(panel.getByRole("button", { name: "list" })).toHaveAttribute("aria-pressed", "true");
    await expect(panel.getByRole("button", { name: /^T3: Write the web app/ })).toHaveAttribute("aria-expanded", "true");
  });

  test("under 820px the graph is not offered", async ({ page }) => {
    await page.setViewportSize({ width: 600, height: 800 });
    await openPlan(page);
    await expect(outputPanel(page).getByRole("button", { name: "graph" })).toBeDisabled();
  });
});
