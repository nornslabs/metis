import { expect, test, type Page, type Route } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { eventStreamBody, seedQueuedRun } from "./support/runs";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

const SPEC_MD = [
  "## Problem",
  "",
  "Founders waste weeks.",
  "",
  "## Target users",
  "",
  "Solo founders.",
  "",
  "## Solution",
  "",
  "None.",
  "",
  "## Key features (MVP and later)",
  "",
  "- Interview",
  "- Research",
  "",
  "## Non-goals",
  "",
  "None.",
  "",
  "## Competitive edge",
  "",
  "None.",
  "",
  "## Success metrics",
  "",
  "None.",
  "",
  "## Risks",
  "",
  "Churn is high.",
  "",
  "## Open questions",
  "",
  "None.",
  "",
].join("\n");

type FakeVersion = {
  id: string;
  idea_id: string;
  number: number;
  source: "agent" | "user";
  content_md: string;
  sections: Record<string, string>;
  run_id: string | null;
  created_by: string | null;
  created_at: string;
};

const version = (ideaId: string, number: number, contentMd: string, source: "agent" | "user" = "agent"): FakeVersion => ({
  id: `sv${number}`,
  idea_id: ideaId,
  number,
  source,
  content_md: contentMd,
  sections: {},
  run_id: null,
  created_by: null,
  created_at: "2026-11-23T10:00:00Z",
});

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function problem(code: string, status: number) {
  return { title: code, code, status, detail: code, retryable: false, errors: [] };
}

interface FakeSpecServer {
  versions: FakeVersion[];
  confirmed: FakeVersion | null;
  saves: { base_number: number; content_md: string }[];
  confirms: number[];
  /** The next save answers `spec.conflict` after `elsewhere` becomes the newest version. */
  conflictWith: string | null;
  /** The next save answers `spec.invalid_transition` after the newest version was confirmed. */
  confirmedElsewhere: boolean;
  /** Spec requests before the draft exists answer with no versions. */
  hidden: boolean;
  /** The next confirm is kept by the server but the run could not be enqueued (503). */
  enqueueFails: boolean;
}

const newest = (server: FakeSpecServer) => server.versions.at(-1) ?? null;

async function fakeSpecIdea(page: Page, options: { confirmed?: boolean; awaiting?: boolean } = {}) {
  const created = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title: `E2E spec ${Date.now()}`, raw_text: `E2E spec ${Date.now()}\nA longer description of the idea.` },
  });
  expect(created.status()).toBe(201);
  const idea = (await created.json()) as { id: string; workspace_id: string };
  const runId = seedQueuedRun(idea.id, idea.workspace_id);
  const draft = version(idea.id, 1, SPEC_MD);
  const server: FakeSpecServer = {
    versions: [draft],
    confirmed: options.confirmed ? draft : null,
    saves: [],
    confirms: [],
    conflictWith: null,
    confirmedElsewhere: false,
    hidden: options.confirmed !== true,
    enqueueFails: false,
  };

  const events: { type: string; data: unknown }[] = [{ type: "node_started", data: { node: "architect" } }];
  if (options.confirmed) events.push({ type: "run_status", data: { status: "succeeded" } });
  else {
    events.push({ type: "interrupt", data: { type: "spec_review", spec_version_id: "sv1", number: 1, kind: "software" } });
    events.push({ type: "run_status", data: { status: "awaiting_user" } });
  }
  await page.route(`**/v1/runs/${runId}/events**`, (route) =>
    route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream" }, body: eventStreamBody(runId, events) }),
  );
  await page.route(`**/v1/ideas/${idea.id}/interview`, (route) => fulfillJson(route, { items: [] }));
  await page.route(`**/v1/ideas/${idea.id}/research`, (route) => fulfillJson(route, problem("research.not_found", 404), 404));
  await page.route(`**/v1/ideas/${idea.id}/scores/latest`, (route) => fulfillJson(route, problem("score.not_found", 404), 404));
  await page.route(`**/v1/ideas/${idea.id}/scores`, (route) => fulfillJson(route, { items: [] }));
  await page.route(`**/v1/ideas/${idea.id}/suggestions`, (route) => fulfillJson(route, { items: [] }));

  await page.route(`**/v1/ideas/${idea.id}/spec`, (route) =>
    fulfillJson(route, server.hidden ? { latest: null, confirmed: null } : { latest: newest(server), confirmed: server.confirmed }),
  );
  await page.route(`**/v1/ideas/${idea.id}/spec/versions`, async (route) => {
    if (route.request().method() === "GET") {
      const items = server.versions
        .map(({ id, number, source, created_by, created_at }) => ({ id, number, source, created_by, created_at }))
        .reverse();
      return fulfillJson(route, { items });
    }
    const body = route.request().postDataJSON() as { base_number: number; content_md: string };
    if (server.confirmedElsewhere) {
      server.confirmed = newest(server);
      return fulfillJson(route, problem("spec.invalid_transition", 409), 409);
    }
    if (server.conflictWith !== null) {
      server.versions.push(version(idea.id, server.versions.length + 1, server.conflictWith, "user"));
      server.conflictWith = null;
      return fulfillJson(route, problem("spec.conflict", 409), 409);
    }
    server.saves.push(body);
    const saved = version(idea.id, server.versions.length + 1, body.content_md, "user");
    server.versions.push(saved);
    return fulfillJson(route, saved, 201);
  });
  await page.route(new RegExp(`/v1/ideas/${idea.id}/spec/versions/\\d+$`), (route) => {
    const number = Number(route.request().url().split("/").pop());
    const found = server.versions.find((candidate) => candidate.number === number);
    return found ? fulfillJson(route, found) : fulfillJson(route, problem("spec.not_found", 404), 404);
  });
  await page.route(`**/v1/ideas/${idea.id}/spec/confirm`, async (route) => {
    const body = route.request().postDataJSON() as { number: number };
    server.confirms.push(body.number);
    server.confirmed = newest(server);
    if (server.enqueueFails) {
      server.enqueueFails = false;
      return fulfillJson(route, problem("run.enqueue_failed", 503), 503);
    }
    return fulfillJson(route, { confirmed: server.confirmed, run_id: runId }, 202);
  });
  return { idea, server, reveal: () => (server.hidden = false) };
}

const outputPanel = (page: Page) => page.getByRole("complementary", { name: "Output" });

async function openIdea(page: Page, options?: { confirmed?: boolean; awaiting?: boolean }) {
  const fake = await fakeSpecIdea(page, options);
  // The draft appears after the page loaded, like a live run: the first read finds nothing.
  await page.goto(`/ideas/${fake.idea.id}`);
  fake.reveal();
  return fake;
}

test.describe("Spec pane", () => {
  test("opens on Spec when the draft arrives live, with the card and the named sections", async ({ page }) => {
    const { idea } = await openIdea(page);
    expect(idea.id).not.toBe("");
    const panel = outputPanel(page);
    await expect(panel.getByRole("tab", { name: /^Spec/ })).toContainText("v1");
    await expect(page.locator('[data-pane="spec"]')).toContainText("Spec draft v1");
    for (const name of ["Problem", "Users", "Core features", "Success metric", "Out of scope", "Risks"]) {
      await expect(panel.getByRole("region", { name })).toBeVisible();
    }
    await expect(panel.getByRole("region", { name: "Solution" })).toHaveCount(0);
    await expect(panel.getByRole("region", { name: "Competitive edge" })).toHaveCount(0);
    await expect(panel.getByText("Click any section to edit. Changes save automatically.")).toBeVisible();
  });

  test("a spec that was already there at load does not open the panel", async ({ page }) => {
    const fake = await fakeSpecIdea(page);
    fake.reveal();
    await page.goto(`/ideas/${fake.idea.id}`);
    await expect(page.locator('[data-pane="spec"]')).toContainText("Spec draft v1");
    await expect(outputPanel(page)).toHaveAttribute("data-open", "false");
  });

  test("saves an edit as a new version that changes only its own section", async ({ page }) => {
    const { server } = await openIdea(page);
    const panel = outputPanel(page);
    const problemField = panel.getByRole("textbox", { name: "Problem" });
    await problemField.fill("Founders ship without checking demand.");

    await expect(panel.getByText("Saved · draft v2, edited")).toBeVisible();
    expect(server.saves).toHaveLength(1);
    expect(server.saves[0]!.base_number).toBe(1);
    expect(server.saves[0]!.content_md).toBe(SPEC_MD.replace("Founders waste weeks.", "Founders ship without checking demand."));

    await page.reload();
    await expect(outputPanel(page).getByRole("textbox", { name: "Problem" })).toHaveValue("Founders ship without checking demand.");
  });

  test("typing quickly saves once; typing during a save saves again on the new version", async ({ page }) => {
    const { server } = await openIdea(page);
    const field = outputPanel(page).getByRole("textbox", { name: "Problem" });
    await field.pressSequentially("Quick typing here", { delay: 20 });
    await expect(outputPanel(page).getByText("Saved · draft v2, edited")).toBeVisible();
    expect(server.saves).toHaveLength(1);

    await field.fill("Second edit");
    await expect(outputPanel(page).getByText("Saved · draft v3, edited")).toBeVisible();
    expect(server.saves.map((save) => save.base_number)).toEqual([1, 2]);
  });

  test("a list adds an item on Enter and saves it as a bullet", async ({ page }) => {
    const { server } = await openIdea(page);
    const panel = outputPanel(page);
    await panel.getByRole("textbox", { name: "Core features, item 2" }).press("Enter");
    await page.keyboard.type("Export to Linear");

    await expect(panel.getByText(/^Saved · draft v/)).toBeVisible();
    await expect.poll(() => server.saves.at(-1)?.content_md ?? "").toContain("- Interview\n- Research\n- Export to Linear");
  });

  test("Esc leaves a field", async ({ page }) => {
    await openIdea(page);
    const field = outputPanel(page).getByRole("textbox", { name: "Problem" });
    await field.focus();
    await page.keyboard.press("Escape");
    await expect(field).not.toBeFocused();
  });

  test("a conflict shows the notice, and Reload shows the newest version", async ({ page }) => {
    const { server } = await openIdea(page);
    const panel = outputPanel(page);
    server.conflictWith = SPEC_MD.replace("Founders waste weeks.", "Changed in another tab.");
    await panel.getByRole("textbox", { name: "Problem" }).fill("Mine");

    await expect(panel.getByRole("alert").filter({ hasText: "Spec changed elsewhere" })).toBeVisible();
    await panel.getByRole("button", { name: "Reload" }).click();
    await expect(panel.getByRole("textbox", { name: "Problem" })).toHaveValue("Changed in another tab.");
    await expect(panel.getByRole("button", { name: "Confirm spec" })).toBeEnabled();
  });

  test("Confirm saves, confirms the newest version and locks the pane", async ({ page }) => {
    const { server } = await openIdea(page);
    const panel = outputPanel(page);
    await panel.getByRole("textbox", { name: "Problem" }).fill("Final problem.");
    await expect(panel.getByText("Saved · draft v2, edited")).toBeVisible();

    await panel.getByRole("button", { name: "Confirm spec" }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toContainText("Confirm spec v2?");
    await dialog.getByRole("button", { name: "Confirm v2" }).click();

    await expect.poll(() => server.confirms).toEqual([2]);
    await expect(panel.getByText("Confirmed · v2")).toBeVisible();
    await expect(panel.getByRole("tab", { name: /^Spec/ })).toContainText("v2 ✓");
    await expect(panel.getByRole("textbox")).toHaveCount(0);
    await expect(panel.getByRole("button", { name: "Confirm spec" })).toHaveCount(0);
  });

  test("a confirmed spec whose run could not continue offers Continue run", async ({ page }) => {
    const { server } = await openIdea(page);
    const panel = outputPanel(page);
    server.enqueueFails = true;
    await panel.getByRole("button", { name: "Confirm spec" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Confirm v1" }).click();

    await expect(panel.getByText("Confirmed, but the run could not continue. Try again.")).toBeVisible();
    await expect(panel.getByRole("textbox")).toHaveCount(0);
    await panel.getByRole("button", { name: "Continue run" }).click();
    await expect.poll(() => server.confirms).toEqual([1, 1]);
    await expect(panel.getByRole("button", { name: "Continue run" })).toHaveCount(0);
  });

  test("the chat prompt confirms the same way and can open the pane", async ({ page }) => {
    const { server } = await openIdea(page);
    const prompt = page.getByRole("group", { name: "Review the spec" });
    await expect(prompt.getByRole("button", { name: "Open the spec" })).toBeVisible();
    await prompt.getByRole("button", { name: "Confirm spec v1" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Confirm v1" }).click();

    await expect.poll(() => server.confirms).toEqual([1]);
    await expect(outputPanel(page).getByText("Confirmed · v1")).toBeVisible();
  });

  test("a confirmed spec opens locked after a reload", async ({ page }) => {
    await openIdea(page, { confirmed: true });
    const panel = outputPanel(page);
    await page.locator('[data-pane="spec"]').click();
    await expect(panel.getByText("Confirmed · v1")).toBeVisible();
    await expect(panel.getByRole("textbox")).toHaveCount(0);
    await expect(panel.getByText("Not set")).toHaveCount(2);
  });

  test("an edit refused because the spec was confirmed elsewhere shows it locked", async ({ page }) => {
    const { server } = await openIdea(page);
    const panel = outputPanel(page);
    server.confirmedElsewhere = true;
    await panel.getByRole("textbox", { name: "Problem" }).fill("Too late");

    await expect(panel.getByText("Confirmed · v1")).toBeVisible();
    await expect(panel.getByRole("textbox")).toHaveCount(0);
  });

  test("the version menu lists every version and shows an older one read-only", async ({
    page,
  }) => {
    const { server } = await openIdea(page);
    const panel = outputPanel(page);
    await panel.getByRole("textbox", { name: "Problem" }).fill("Second text.");
    await expect(panel.getByText("Saved · draft v2, edited")).toBeVisible();

    await panel.getByRole("button", { name: "Versions" }).click();
    await expect(page.getByRole("menuitemradio")).toHaveCount(2);
    await expect(
      page.getByRole("menuitemradio", { name: /^v2/ }),
    ).toBeChecked();
    await page.getByRole("menuitemradio", { name: /^v1/ }).click();

    await expect(
      panel.getByText("Viewing v1 by Agent, read-only."),
    ).toBeVisible();
    await expect(panel.getByRole("textbox")).toHaveCount(0);
    await expect(panel.getByText("Founders waste weeks.")).toBeVisible();
    await expect(
      panel.getByRole("button", { name: "Confirm spec" }),
    ).toBeDisabled();

    await panel.getByRole("button", { name: "Back to v2" }).click();
    await expect(panel.getByRole("textbox", { name: "Problem" })).toHaveValue(
      "Second text.",
    );
    await expect(
      panel.getByRole("button", { name: "Confirm spec" }),
    ).toBeEnabled();
    expect(server.saves).toHaveLength(1);
  });

  test("text typed before switching to an older version is saved first and kept", async ({
    page,
  }) => {
    const { server } = await openIdea(page);
    const panel = outputPanel(page);
    await panel
      .getByRole("textbox", { name: "Problem" })
      .fill("Typed just now.");
    await panel.getByRole("button", { name: "Versions" }).click();
    await page.getByRole("menuitemradio", { name: /^v1/ }).click();
    await expect(
      panel.getByText("Viewing v1 by Agent, read-only."),
    ).toBeVisible();
    expect(server.saves.map((save) => save.base_number)).toEqual([1]);

    await panel.getByRole("button", { name: "Back to v2" }).click();
    await expect(panel.getByRole("textbox", { name: "Problem" })).toHaveValue(
      "Typed just now.",
    );
  });

  test("Restore as a new version saves the old text on the newest number", async ({
    page,
  }) => {
    const { server } = await openIdea(page);
    const panel = outputPanel(page);
    await panel.getByRole("textbox", { name: "Problem" }).fill("Changed.");
    await expect(panel.getByText("Saved · draft v2, edited")).toBeVisible();
    await panel.getByRole("button", { name: "Versions" }).click();
    await page.getByRole("menuitemradio", { name: /^v1/ }).click();
    await panel.getByRole("button", { name: "Restore as v3" }).click();

    await expect(panel.getByText("Saved · draft v3, edited")).toBeVisible();
    expect(server.saves.at(-1)).toEqual({
      base_number: 2,
      content_md: SPEC_MD,
    });
    await expect(panel.getByRole("textbox", { name: "Problem" })).toHaveValue(
      "Founders waste weeks.",
    );
  });

  test("Restore is not offered when the spec is confirmed", async ({
    page,
  }) => {
    await openIdea(page);
    const panel = outputPanel(page);
    await panel.getByRole("textbox", { name: "Problem" }).fill("Final.");
    await expect(panel.getByText("Saved · draft v2, edited")).toBeVisible();
    await panel.getByRole("button", { name: "Confirm spec" }).click();
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "Confirm v2" })
      .click();
    await expect(panel.getByText("Confirmed · v2")).toBeVisible();

    await panel.getByRole("button", { name: "Versions" }).click();
    await expect(
      page.getByRole("menuitemradio", { name: /Confirmed/ }),
    ).toContainText("v2");
    await page.getByRole("menuitemradio", { name: /^v1/ }).click();
    await expect(
      panel.getByText("Viewing v1 by Agent, read-only."),
    ).toBeVisible();
    await expect(
      panel.getByRole("button", { name: /^Restore as/ }),
    ).toHaveCount(0);
  });

  test("Compare shows what changed between two versions", async ({ page }) => {
    await openIdea(page);
    const panel = outputPanel(page);
    await expect(panel.getByRole("button", { name: "Compare" })).toBeDisabled();
    await panel
      .getByRole("textbox", { name: "Problem" })
      .fill("Founders lose weeks.");
    await expect(panel.getByText("Saved · draft v2, edited")).toBeVisible();

    await panel.getByRole("button", { name: "Compare" }).click();
    await expect(panel.getByRole("combobox")).toHaveValue("1");
    const problemChanges = panel.getByRole("region", {
      name: "Problem, changes",
    });
    await expect(problemChanges.locator("del")).toHaveText("deleted: waste");
    await expect(problemChanges.locator("ins")).toHaveText("inserted: lose");
    await expect(
      panel.getByRole("region", { name: "Users, changes" }),
    ).toContainText("No changes");
    await expect(panel.getByText("1 added")).toBeVisible();

    await panel.getByRole("button", { name: "Compare" }).click();
    await expect(panel.getByRole("textbox", { name: "Problem" })).toHaveValue(
      "Founders lose weeks.",
    );
  });

  test("a version that fails to load shows Retry", async ({ page }) => {
    await openIdea(page);
    const panel = outputPanel(page);
    await panel.getByRole("textbox", { name: "Problem" }).fill("Another.");
    await expect(panel.getByText("Saved · draft v2, edited")).toBeVisible();
    let fail = true;
    await page.route(/\/spec\/versions\/1$/, (route) => {
      if (!fail) return route.fallback();
      return fulfillJson(route, problem("internal_error", 500), 500);
    });
    await panel.getByRole("button", { name: "Versions" }).click();
    await page.getByRole("menuitemradio", { name: /^v1/ }).click();
    await expect(
      panel
        .getByRole("alert")
        .filter({ hasText: "Could not load the spec v1" }),
    ).toBeVisible();
    fail = false;
    await panel.getByRole("button", { name: "Retry" }).click();
    await expect(
      panel.getByText("Viewing v1 by Agent, read-only."),
    ).toBeVisible();
  });

  test("Esc closes the version menu", async ({ page }) => {
    await openIdea(page);
    const panel = outputPanel(page);
    await panel.getByRole("button", { name: "Versions" }).click();
    await expect(page.getByRole("menuitemradio")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("menuitemradio")).toHaveCount(0);
  });

  test("Confirm is off while comparing, and Restore is off when the text equals the newest", async ({ page }) => {
    const { server } = await openIdea(page);
    const panel = outputPanel(page);
    await panel.getByRole("textbox", { name: "Problem" }).fill("Middle text.");
    await expect(panel.getByText("Saved · draft v2, edited")).toBeVisible();
    await panel.getByRole("textbox", { name: "Problem" }).fill("Founders waste weeks.");
    await expect(panel.getByText("Saved · draft v3, edited")).toBeVisible();
    expect(server.saves).toHaveLength(2);

    await panel.getByRole("button", { name: "Compare" }).click();
    await expect(panel.getByRole("button", { name: "Confirm spec" })).toBeDisabled();
    await panel.getByRole("combobox").selectOption("1");
    await expect(panel.getByRole("region", { name: "Problem, changes" })).toContainText("No changes");

    await panel.getByRole("button", { name: "Versions" }).click();
    await page.getByRole("menuitemradio", { name: /^v1/ }).click();
    await expect(panel.getByRole("button", { name: "Restore as v4" })).toBeDisabled();
  });

  test("a conflict while restoring shows the conflict notice", async ({ page }) => {
    const { server } = await openIdea(page);
    const panel = outputPanel(page);
    await panel.getByRole("textbox", { name: "Problem" }).fill("Changed.");
    await expect(panel.getByText("Saved · draft v2, edited")).toBeVisible();
    await panel.getByRole("button", { name: "Versions" }).click();
    await page.getByRole("menuitemradio", { name: /^v1/ }).click();
    server.conflictWith = SPEC_MD.replace("Founders waste weeks.", "Elsewhere.");
    await panel.getByRole("button", { name: "Restore as v3" }).click();

    await expect(panel.getByRole("alert").filter({ hasText: "Spec changed elsewhere" })).toBeVisible();
  });
});
