import { expect, test, type Page } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

const CONNECTED = {
  provider: "linear",
  status: "connected",
  scopes: [],
  expires_at: null,
  connected_at: "2026-11-20T10:00:00Z",
  connected_by: null,
  version: 1,
};

async function mockIntegrations(page: Page, items: readonly object[]) {
  await page.route("**/v1/integrations", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items }) }),
  );
}

test.describe("integrations tab", () => {
  test("a connected Linear lists its tools and offers Disconnect", async ({ page }) => {
    await mockIntegrations(page, [CONNECTED]);
    await page.route("**/v1/integrations/linear/tools", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [{ name: "save_issue", description: "Create or update an issue" }] }),
      }),
    );
    await page.goto("/?settings=integrations");

    await expect(page.getByText("Connected", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Disconnect" })).toBeVisible();
    await page.getByRole("button", { name: "Tools" }).click();
    await expect(page.getByText("save_issue")).toBeVisible();
  });

  test("an expired Linear asks to reconnect and its tools say so, not an error", async ({ page }) => {
    await mockIntegrations(page, [{ ...CONNECTED, status: "expired" }]);
    await page.route("**/v1/integrations/linear/tools", (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/problem+json",
        body: JSON.stringify({ title: "Expired", code: "mcp.expired", status: 409 }),
      }),
    );
    await page.goto("/?settings=integrations");

    await expect(page.getByRole("button", { name: "Reconnect" })).toBeVisible();
    await page.getByRole("button", { name: "Tools" }).click();
    await expect(page.getByText("Reconnect to load tools.")).toBeVisible();
  });

  test("Notion's Connect is off with a reason", async ({ page }) => {
    await mockIntegrations(page, []);
    await page.goto("/?settings=integrations");

    const notion = page.getByRole("button", { name: "Connect" }).last();
    await expect(notion).toBeDisabled();
    await expect(notion).toHaveAttribute("title", "Notion export is not available yet");
  });

  test("an error return shows a message and clears the params", async ({ page }) => {
    await mockIntegrations(page, []);
    await page.goto("/?settings=integrations&integration_error=mcp.oauth_failed");

    await expect(page.getByText("Linear did not accept the connection.")).toBeVisible();
    await expect(page).not.toHaveURL(/integration_error/);
    await expect(page).toHaveURL(/settings=integrations/);
  });

  test("Connect sends the browser to the address the server gives", async ({ page }) => {
    await mockIntegrations(page, []);
    let body: unknown = null;
    await page.route("**/v1/integrations/linear/connect", async (route) => {
      body = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ authorize_url: "http://127.0.0.1:9/authorize" }),
      });
    });
    await page.goto("/?settings=integrations");
    await page.getByRole("button", { name: "Connect" }).first().click();

    await expect.poll(() => body).toMatchObject({ redirect_to: expect.stringContaining("settings=integrations") });
  });
});
