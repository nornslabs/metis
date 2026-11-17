import { expect, test } from "@playwright/test";

import { SESSION_COOKIE, USER_EMAIL, createSessionToken } from "./support/session";

test.describe("signed out", () => {
  test("visiting / redirects to the sign-in page", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/sign-in$/);
    await expect(page.getByRole("heading", { name: "Sign in to Metis" })).toBeVisible();
  });

  test("offers Google as a link to the server login route and email as Soon", async ({ page }) => {
    await page.goto("/sign-in");
    const google = page.getByRole("link", { name: "Continue with Google" });
    await expect(google).toHaveAttribute("href", "/v1/auth/google/login?redirect_to=%2F");
    await expect(page.getByLabel(/Email/)).toBeDisabled();
    await expect(page.getByText("Soon")).toBeVisible();
  });

  test("keeps the page the user asked for in the login link", async ({ page }) => {
    await page.goto("/sign-in?redirect_to=%2Fideas%2Fabc");
    await expect(page.getByRole("link", { name: "Continue with Google" })).toHaveAttribute(
      "href",
      "/v1/auth/google/login?redirect_to=%2Fideas%2Fabc",
    );
  });

  test("ignores an off-site redirect_to", async ({ page }) => {
    await page.goto("/sign-in?redirect_to=%2F%2Fevil.com");
    await expect(page.getByRole("link", { name: "Continue with Google" })).toHaveAttribute(
      "href",
      "/v1/auth/google/login?redirect_to=%2F",
    );
  });

  test("shows a friendly message for a failed sign-in", async ({ page }) => {
    await page.goto("/sign-in?error=auth.oauth_failed");
    await expect(page.getByRole("alert").filter({ hasText: "Google sign-in failed" })).toHaveText(
      "Google sign-in failed. Try again.",
    );
  });

  test("links to the terms and privacy pages, which are public", async ({ page }) => {
    await page.goto("/sign-in");
    await expect(page.getByText(/By continuing you agree to the/)).toBeVisible();
    await page.getByRole("link", { name: "Terms", exact: true }).click();
    await expect(page).toHaveURL(/\/terms$/);
    await expect(page.getByRole("heading", { name: "Terms of Use" })).toBeVisible();
    await page.getByRole("link", { name: "Privacy Policy" }).click();
    await expect(page).toHaveURL(/\/privacy$/);
    await expect(page.getByRole("heading", { name: "Privacy Policy" })).toBeVisible();
    await page.getByRole("link", { name: "← Back to sign in" }).click();
    await expect(page).toHaveURL(/\/sign-in$/);
  });

  test("legal pages have no horizontal scroll at 375px", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    for (const path of ["/terms", "/privacy"]) {
      await page.goto(path);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);
    }
  });

  test("has no horizontal scroll at 375px", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto("/sign-in");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
    const formTop = await page.getByRole("heading", { name: "Sign in to Metis" }).boundingBox();
    const pitchTop = await page.getByRole("heading", { name: /Know if your idea/ }).boundingBox();
    expect(formTop!.y).toBeLessThan(pitchTop!.y);
  });
});

test.describe("signed in", () => {
  let sessionToken = "";

  test.beforeEach(async ({ context, baseURL }) => {
    sessionToken = createSessionToken();
    await context.addCookies([
      { name: SESSION_COOKIE, value: sessionToken, url: baseURL!, httpOnly: true, sameSite: "Lax" },
    ]);
  });

  test("shows the app and sends the sign-in page back to it", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(`Signed in as ${USER_EMAIL}.`)).toBeVisible();
    await page.goto("/sign-in?redirect_to=%2F");
    await expect(page).toHaveURL(/\/$/);
  });

  test("never exposes the session token to JavaScript", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(`Signed in as ${USER_EMAIL}.`)).toBeVisible();
    expect(await page.evaluate(() => document.cookie)).not.toContain(sessionToken);
  });

  test("sign out ends the session on the server", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/sign-in$/);
    const me = await page.request.get("/v1/auth/me");
    expect(me.status()).toBe(401);
  });

  test("useMe reads the user with only the session cookie", async ({ page }) => {
    const authorization: string[] = [];
    page.on("request", (request) => {
      const value = request.headers()["authorization"];
      if (value) authorization.push(value);
    });
    await page.goto("/");
    await expect(page.getByText(`Signed in as ${USER_EMAIL}.`)).toBeVisible();
    expect(authorization).toEqual([]);
  });

  test("a session that ends mid-visit sends the user to sign-in with a notice", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByText(`Signed in as ${USER_EMAIL}.`)).toBeVisible();
    await page.request.post("/v1/auth/logout", { headers: { "X-Metis-Client": "web" } });
    // Tab focus makes TanStack Query refetch `useMe()`, which now answers 401.
    await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
    await expect(page).toHaveURL(/\/sign-in/);
    await expect(page.getByText("Signed out")).toBeVisible();
  });
});

