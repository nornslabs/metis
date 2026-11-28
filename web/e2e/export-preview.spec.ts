import { expect, test, type Page, type Route } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { eventStreamBody, seedAwaitingRun, seedQueuedRun } from "./support/runs";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };

const BRIEF =
  "## Goal\n\nSign people in.\n\n<script>window.pwned = true</script>\n\n![x](https://evil.example/x.png)\n\n>>> Agent notes\n\nTouch the auth module.\n\n>>>";

const PREVIEW = {
  team: { id: "t1", name: "Ship" },
  plan_version: 3,
  project: { name: "Metis", action: "create" },
  hld: { title: "Metis HLD", action: "create" },
  milestones: { total: 1, create: 1, update: 0, items: [{ name: "Phase 1", action: "create" }] },
  issues: {
    total: 2,
    create: 2,
    update: 0,
    items: [
      { title: "Add sign-in", description: BRIEF, component: "Auth" },
      { title: "Add billing", description: "## Goal\n\nCharge people.", component: null },
    ],
  },
  blocked_by_links: 0,
  labels: { total: 0, items: [] },
};

const HLD_TEXT =
  "## Overview\n\nText.\n\n## MVP components\n\n### Auth\n\n**Purpose:** Sign in.\n\n### Billing\n\n**Purpose:** Pay.";

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

/** An idea paused on `export_approval` with `preview`; `hld` is what `GET /spec` returns for it. */
async function pausedExport(page: Page, preview: Record<string, unknown>, hld: Record<string, unknown> | null) {
  const created = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title: `E2E export ${Date.now()}`, raw_text: "A longer description of the idea for the export test." },
  });
  expect(created.status()).toBe(201);
  const idea = (await created.json()) as { id: string; workspace_id: string };
  const runId = seedQueuedRun(idea.id, idea.workspace_id);
  const payload = { type: "export_approval", preview };
  seedAwaitingRun(runId, payload);
  await page.route(`**/v1/runs/${runId}/events**`, (route) =>
    route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: eventStreamBody(runId, [
        { type: "interrupt", data: payload },
        { type: "run_status", data: { status: "awaiting_user" } },
      ]),
    }),
  );
  await page.route(`**/v1/ideas/${idea.id}/interview`, (route) => fulfillJson(route, { items: [] }));
  await page.route(`**/v1/ideas/${idea.id}/spec`, (route) =>
    fulfillJson(route, { latest: null, confirmed: null, hld }),
  );
  const bodies: unknown[] = [];
  await page.route(`**/v1/runs/${runId}/resume`, (route) => {
    bodies.push(route.request().postDataJSON());
    return fulfillJson(route, { run_id: runId }, 202);
  });
  await page.goto(`/ideas/${idea.id}`);
  await page.getByRole("button", { name: "Review the export" }).click();
  return { bodies, dialog: page.getByRole("dialog") };
}

const HLD = { build_language: "Python", content_md: HLD_TEXT, stale: false };

test.describe("export preview dialog", () => {
  test("shows the name with its count and refuses a name over 80 characters", async ({ page }) => {
    const { bodies, dialog } = await pausedExport(page, PREVIEW, HLD);
    const name = dialog.getByLabel("Project name");
    const approve = dialog.getByRole("button", { name: "Approve" });

    await expect(name).toHaveValue("Metis");
    await expect(dialog.getByText("5 / 80")).toBeVisible();

    await name.fill("a".repeat(81));
    await expect(dialog.getByText("81 / 80")).toBeVisible();
    await expect(dialog.getByText("Use 80 characters or fewer.")).toBeVisible();
    await expect(approve).toBeDisabled();

    await name.fill("   ");
    await expect(dialog.getByText("Enter a name.")).toBeVisible();
    await expect(approve).toBeDisabled();
    expect(bodies).toEqual([]);

    await name.fill("  Orbit  ");
    await approve.click();
    await expect.poll(() => bodies).toEqual([{ value: { approved: true, project_name: "Orbit" } }]);
  });

  test("Cancel declines without a name", async ({ page }) => {
    const { bodies, dialog } = await pausedExport(page, PREVIEW, HLD);
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect.poll(() => bodies).toEqual([{ value: { approved: false } }]);
  });

  test("Esc never answers and the typed name survives reopening", async ({ page }) => {
    const { bodies, dialog } = await pausedExport(page, PREVIEW, HLD);
    await dialog.getByLabel("Project name").fill("Orbit");
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    expect(bodies).toEqual([]);

    await page.getByRole("button", { name: "Review the export" }).click();
    await expect(page.getByRole("dialog").getByLabel("Project name")).toHaveValue("Orbit");
  });

  test("each issue opens to its brief, with Agent notes apart and no injected HTML", async ({ page }) => {
    const { dialog } = await pausedExport(page, PREVIEW, HLD);
    const row = dialog.getByRole("button", { name: /Add sign-in/ });
    await expect(row).toHaveAttribute("aria-expanded", "false");
    await row.click();
    await expect(row).toHaveAttribute("aria-expanded", "true");

    await expect(dialog.getByText("Sign people in.")).toBeVisible();
    const notes = dialog.getByRole("region", { name: "Agent notes" });
    await expect(notes.getByText("Touch the auth module.")).toBeVisible();
    await expect(dialog.getByText(">>>")).toHaveCount(0);
    await expect(dialog.locator("script, img")).toHaveCount(0);
    expect(await page.evaluate(() => (window as unknown as { pwned?: boolean }).pwned)).toBeUndefined();
  });

  test("a software idea shows the HLD, its components and the full text", async ({ page }) => {
    const { dialog } = await pausedExport(page, PREVIEW, HLD);
    const hld = dialog.getByRole("region", { name: "HLD" });
    await expect(hld.getByText("Metis HLD")).toBeVisible();
    await expect(hld.getByText("Language · Python")).toBeVisible();
    await expect(hld.getByRole("list", { name: "Components" }).getByRole("listitem")).toHaveText(["Auth", "Billing"]);
    await hld.getByRole("button", { name: "Read the HLD" }).click();
    await expect(hld.getByText("Sign in.")).toBeVisible();
    await expect(hld.getByRole("textbox")).toHaveCount(0);
  });

  test("a stale HLD shows a note and Approve stays on", async ({ page }) => {
    const { dialog } = await pausedExport(page, PREVIEW, { ...HLD, stale: true });
    await expect(dialog.getByText("The HLD was written for an earlier spec.")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Approve" })).toBeEnabled();
  });

  test("a non-software idea shows no HLD", async ({ page }) => {
    const { dialog } = await pausedExport(page, { ...PREVIEW, hld: null }, null);
    await expect(dialog.getByRole("region", { name: "HLD" })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: /Add sign-in/ })).toBeVisible();
  });
});
