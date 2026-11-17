import { expect, test, type Page } from "@playwright/test";

import { SESSION_COOKIE, USER_EMAIL, createSessionToken, seedMemberWorkspace } from "./support/session";

const SECRET_LLM = "sk-e2e-plaintext-llm-0001";
const SECRET_EXA = "exa-e2e-plaintext-0002";
// Nothing listens here: the key test fails with `unreachable`.
const DEAD_BASE_URL = "http://127.0.0.1:9/v1";

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    {
      name: SESSION_COOKIE,
      value: createSessionToken(),
      url: baseURL!,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
});

async function openSettings(page: Page, tab: string) {
  await page.goto(`/?settings=${tab}`);
  await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
}

async function removeKeyIfSaved(page: Page, kind: "llm" | "exa") {
  await page.request.delete(`/v1/settings/keys/${kind}`, { headers: { "X-Metis-Client": "web" } });
}

test.describe("shell", () => {
  test("frames the empty chat and shows who is signed in", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "What are you building?" })).toBeVisible();
    await expect(page.getByText("Beta")).toBeVisible();
    await expect(page.getByRole("link", { name: "New idea" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
    await page.getByRole("button", { name: "Account" }).click();
    await expect(page.getByText(USER_EMAIL)).toBeVisible();
  });

  test("has no horizontal scroll at 375px, with the sheet open too", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    for (const path of ["/", "/?settings=keys"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: "What are you building?" })).toBeAttached();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);
    }
  });
});

test.describe("settings sheet", () => {
  test("deep link opens the tab; Esc closes it and returns focus", async ({ page }) => {
    await openSettings(page, "keys");
    await expect(page.getByRole("tab", { name: "API keys" })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeHidden();
    await expect(page).not.toHaveURL(/settings=/);
    await expect(page.getByRole("button", { name: "Account" })).toBeFocused();
  });

  test("an unknown tab opens Account; the keyboard shortcut opens the sheet", async ({ page }) => {
    await page.goto("/?settings=nope");
    await expect(page.getByRole("tab", { name: "Account" })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Escape");
    await page.keyboard.press("ControlOrMeta+,");
    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
  });

  test("the account tab is read-only", async ({ page }) => {
    await openSettings(page, "account");
    await expect(page.getByLabel("Email")).toHaveValue(USER_EMAIL);
    await expect(page.getByLabel("Email")).toHaveAttribute("readonly", "");
  });

  test("integrations says Soon and preferences holds the theme", async ({ page }) => {
    await openSettings(page, "integrations");
    await expect(page.getByText("Soon")).toBeVisible();
    await page.getByRole("tab", { name: "Preferences" }).click();
    await page.getByRole("button", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
  });
});

test.describe("api keys", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await removeKeyIfSaved(page, "llm");
    await removeKeyIfSaved(page, "exa");
  });

  test("saves keys masked, never shows plaintext, tests, and removes", async ({ page }) => {
    await openSettings(page, "keys");
    await page.getByLabel("Base URL").fill(DEAD_BASE_URL);
    await page.getByLabel("Model").fill("test-model");
    await page.getByLabel("API key", { exact: true }).fill(SECRET_LLM);
    await page.getByLabel("Exa API key").fill(SECRET_EXA);
    await page.getByRole("button", { name: "Save changes" }).click();

    await expect(page.getByTestId("saved-llm")).toBeVisible();
    await expect(page.getByTestId("saved-exa")).toBeVisible();
    await expect(page.getByLabel("Exa API key")).toHaveCount(0);
    const html = await page.content();
    expect(html).not.toContain(SECRET_LLM);
    expect(html).not.toContain(SECRET_EXA);
    await expect(page.getByTestId("saved-llm")).toContainText("…");

    await page.getByRole("button", { name: "Test" }).first().click();
    await expect(page.getByRole("alert").filter({ hasText: /Couldn't reach the provider/ })).toBeVisible();

    await page.getByRole("button", { name: "Remove" }).first().click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Remove" }).click();
    await expect(page.getByLabel("Base URL")).toBeVisible();
  });

  test("blocks an LLM key without a base URL and model", async ({ page }) => {
    await openSettings(page, "keys");
    await page.getByLabel("API key", { exact: true }).fill(SECRET_LLM);
    await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled();
    await expect(page.getByText(/Enter a full URL/)).toBeVisible();
  });
});

test.describe("run limits", () => {
  test("saves budget and steps, blocks bad values, and reloads on a stale version", async ({
    page,
  }) => {
    await openSettings(page, "keys");
    await page.getByLabel("Budget per run (USD)").fill("0");
    await expect(page.getByText(/Enter an amount above 0/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled();

    await page.getByLabel("Budget per run (USD)").fill("3.5");
    await page.getByLabel("Max steps per run").fill("40");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Settings saved")).toBeVisible();
    await expect(page.getByLabel("Budget per run (USD)")).toHaveValue("3.50");

    const current = await (await page.request.get("/v1/settings")).json();
    expect(current.settings.max_steps).toBe(40);

    // Someone else changes the settings while this sheet still holds the old version.
    await page.getByLabel("Max steps per run").fill("41");
    await page.request.patch("/v1/settings", {
      headers: { "X-Metis-Client": "web" },
      data: { version: current.settings.version, max_steps: 60 },
    });
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Settings changed elsewhere; reloaded.")).toBeVisible();
    await expect(page.getByLabel("Max steps per run")).toHaveValue("60");
  });
});

test.describe("workspaces", () => {
  test("creates a workspace, switches to it and keeps the choice after a reload", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Account" }).click();
    // The submenu trigger reads "Workspace" while loading, then the current workspace ("Personal").
    await page.getByRole("menuitem", { name: /^(Workspace|Personal)$/ }).click();
    await page.getByRole("menuitem", { name: "New workspace" }).click();
    const name = `E2E ${Date.now()}`;
    await page.getByLabel("Workspace name").fill(name);
    await page.getByRole("button", { name: "Create workspace" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();

    await page.reload();
    await page.getByRole("button", { name: "Account" }).click();
    // The submenu trigger shows the current workspace.
    await expect(page.getByRole("menuitem", { name })).toBeVisible();

    const cookies = await page.context().cookies();
    const chosen = cookies.find((cookie) => cookie.name === "metis_workspace");
    expect(chosen).toBeDefined();
    const current = await page.request.get("/v1/workspaces/current", {
      headers: { "X-Workspace-Id": chosen!.value },
    });
    expect((await current.json()).workspace.name).toBe(name);
  });
});

test.describe("member", () => {
  test("sees keys and limits read-only", async ({ page, context, baseURL }) => {
    const workspaceId = seedMemberWorkspace();
    await context.addCookies([{ name: "metis_workspace", value: workspaceId, url: baseURL! }]);
    await openSettings(page, "keys");
    await expect(page.getByText("Only workspace owners can change keys.")).toBeVisible();
    await expect(page.getByLabel("Budget per run (USD)")).toHaveAttribute("readonly", "");
    await expect(page.getByRole("button", { name: "Save changes" })).toHaveCount(0);
  });
});

test.describe("signing out", () => {
  test("Sign out all devices ends the session on the server", async ({ page }) => {
    await openSettings(page, "account");
    await page.getByRole("button", { name: "Sign out all" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Sign out all" }).click();
    await expect(page).toHaveURL(/\/sign-in/);
    const me = await page.request.get("/v1/auth/me");
    expect(me.status()).toBe(401);
  });
});
