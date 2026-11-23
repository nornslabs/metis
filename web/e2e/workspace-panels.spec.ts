import { expect, test, type Page } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { crossesTick, tickCentres } from "./support/ticks";

const LAPTOP = { width: 1440, height: 900 };
const SMALL_LAPTOP = { width: 1100, height: 800 };
const PHONE = { width: 375, height: 800 };
const HISTORY_WIDTH_PX = 264;
const TOGGLE_SIZE_PX = 28;
const PHONE_CORNER_INSET_PX = 8;
const GEOMETRY_TOLERANCE_PX = 1.5;

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
});

const historyToggle = (page: Page) => page.getByRole("button", { name: "Your ideas" });
const outputToggle = (page: Page) => page.getByRole("button", { name: "Outputs" });
const historyPanel = (page: Page) => page.getByRole("complementary", { name: "Ideas" });
const outputPanel = (page: Page) => page.getByRole("complementary", { name: "Output" });

async function openApp(page: Page, size: { width: number; height: number }, path = "/") {
  await page.setViewportSize(size);
  await page.goto(path);
  await expect(page.getByLabel("Your idea")).toBeVisible();
}

async function boxOf(locator: ReturnType<Page["locator"]>) {
  const box = await locator.boundingBox();
  if (!box) throw new Error("element has no box");
  return box;
}

test.describe("workspace panels", () => {
  test("the left toggle opens history, pushes the chat and gives way to the panel's own close button", async ({ page }) => {
    await openApp(page, LAPTOP);
    const paneBefore = await boxOf(page.locator("[data-frame=column]"));

    await historyToggle(page).click();

    await expect(historyPanel(page)).toHaveAttribute("data-open", "true");
    await expect(historyToggle(page)).toBeHidden();
    await expect(page.getByRole("button", { name: "Close history" })).toBeVisible();
    await expect.poll(async () => (await boxOf(historyPanel(page))).width).toBeCloseTo(HISTORY_WIDTH_PX, 0);
    const paneAfter = await boxOf(page.locator("[data-frame=column]"));
    expect(paneAfter.x).toBeLessThan(paneBefore.x + GEOMETRY_TOLERANCE_PX);
  });

  test("Esc closes the top-most panel and focus returns to its toggle", async ({ page }) => {
    await openApp(page, LAPTOP);
    await historyToggle(page).click();
    await expect(historyPanel(page)).toHaveAttribute("data-open", "true");

    await page.keyboard.press("Escape");

    await expect(historyPanel(page)).toHaveAttribute("data-open", "false");
    await expect(historyToggle(page)).toBeFocused();
  });

  test("Esc closes the panel opened last when both are open", async ({ page }) => {
    await openApp(page, LAPTOP, "/?panel=score");
    await expect(outputPanel(page)).toHaveAttribute("data-open", "true");
    await historyToggle(page).click();
    await expect(historyPanel(page)).toHaveAttribute("data-open", "true");

    await page.keyboard.press("Escape");
    await expect(historyPanel(page)).toHaveAttribute("data-open", "false");
    await expect(outputPanel(page)).toHaveAttribute("data-open", "true");

    await page.keyboard.press("Escape");
    await expect(outputPanel(page)).toHaveAttribute("data-open", "false");
  });

  test("Esc inside the composer leaves the panels open", async ({ page }) => {
    await openApp(page, LAPTOP);
    await historyToggle(page).click();
    await page.getByLabel("Your idea").focus();

    await page.keyboard.press("Escape");

    await expect(historyPanel(page)).toHaveAttribute("data-open", "true");
  });

  test("the / key opens history, but not while typing", async ({ page }) => {
    await openApp(page, LAPTOP);
    await page.getByLabel("Your idea").fill("a");
    await page.keyboard.type("/");
    await expect(historyPanel(page)).toHaveAttribute("data-open", "false");

    await page.locator("body").click({ position: { x: 5, y: 300 } });
    await page.keyboard.press("/");

    await expect(historyPanel(page)).toHaveAttribute("data-open", "true");
  });

  test("under 1200px one panel closes the other; from 1200px both stay open", async ({ page }) => {
    await openApp(page, SMALL_LAPTOP, "/?panel=score");
    await historyToggle(page).click();
    await expect(historyPanel(page)).toHaveAttribute("data-open", "true");
    await expect(outputPanel(page)).toHaveAttribute("data-open", "false");
    await expect(page).not.toHaveURL(/panel=/);

    await openApp(page, LAPTOP, "/?panel=score");
    await historyToggle(page).click();
    await expect(historyPanel(page)).toHaveAttribute("data-open", "true");
    await expect(outputPanel(page)).toHaveAttribute("data-open", "true");
  });

  test("?panel= opens the output panel on that pane, an unknown value opens nothing, closing clears it", async ({ page }) => {
    await openApp(page, LAPTOP, "/?panel=spec");
    await expect(outputPanel(page)).toHaveAttribute("data-open", "true");
    await expect(page.getByRole("tab", { name: "Spec" })).toHaveAttribute("aria-selected", "true");

    await page.getByRole("button", { name: "Close output" }).click();
    await expect(outputPanel(page)).toHaveAttribute("data-open", "false");
    await expect(page).not.toHaveURL(/panel=/);

    await openApp(page, LAPTOP, "/?panel=nope");
    await expect(outputPanel(page)).toHaveAttribute("data-open", "false");
  });

  test("the output toggle is disabled with no output and has no unseen dot", async ({ page }) => {
    await openApp(page, LAPTOP);

    await expect(outputToggle(page)).toBeDisabled();
    await expect(page.getByTestId("output-unseen-dot")).toHaveCount(0);
  });

  test("toggles straddle the column guides and ticks sit on every crossing, with panels open or not", async ({ page }) => {
    await openApp(page, LAPTOP);
    const states: Array<() => Promise<void>> = [
      async () => {},
      async () => historyToggle(page).click(),
      async () => page.goto("/?panel=score").then(() => historyToggle(page).click()),
    ];

    for (const arrange of states) {
      await arrange();
      await page.waitForTimeout(400); // panels animate for 250ms
      const lines = await page.evaluate(() => {
        const rectOf = (selector: string) => document.querySelector(selector)?.getBoundingClientRect();
        const open = (part: string) => rectOf(`[data-frame=${part}][data-open=true]`);
        const column = rectOf("[data-frame=column]")!;
        return {
          xs: [rectOf("[data-frame=safe]")!.left, rectOf("[data-frame=safe]")!.right, column.left, column.right],
          panelXs: [open("history")?.right, open("output")?.left].filter((x): x is number => x !== undefined),
          headerY: rectOf("[data-frame=header]")!.bottom,
          footerY: rectOf("[data-frame=footer]")!.top,
        };
      });
      const ticks = await tickCentres(page);
      for (const x of [...lines.xs, ...lines.panelXs]) {
        expect(crossesTick(ticks, x, lines.headerY)).toBe(true);
        expect(crossesTick(ticks, x, lines.footerY)).toBe(true);
      }
    }
  });

  test("the toggles' centres sit on the column guides", async ({ page }) => {
    await openApp(page, LAPTOP);
    const column = await boxOf(page.locator("[data-frame=column]"));

    const left = await boxOf(historyToggle(page));
    const right = await boxOf(outputToggle(page));

    expect(Math.abs(left.x + TOGGLE_SIZE_PX / 2 - column.x)).toBeLessThanOrEqual(GEOMETRY_TOLERANCE_PX);
    expect(Math.abs(right.x + TOGGLE_SIZE_PX / 2 - (column.x + column.width))).toBeLessThanOrEqual(
      GEOMETRY_TOLERANCE_PX,
    );
  });

  test("on a phone panels are overlays with a scrim and the toggles sit inside the corners", async ({ page }) => {
    await openApp(page, PHONE);
    const left = await boxOf(historyToggle(page));
    expect(left.x).toBeCloseTo(PHONE_CORNER_INSET_PX, 0);

    await historyToggle(page).click();
    await expect(page.getByTestId("history-scrim")).toBeVisible();
    await expect(page.getByRole("button", { name: "Close history" })).toBeFocused();
    const noOverflow = () =>
      page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
    expect(await noOverflow()).toBe(true);

    await page.getByTestId("history-scrim").click({ position: { x: PHONE.width - 10, y: 400 } });
    await expect(historyPanel(page)).toHaveAttribute("data-open", "false");

    await page.goto("/?panel=score");
    const output = await boxOf(outputPanel(page));
    expect(output.width).toBeCloseTo(PHONE.width, 0);
    await page.getByRole("button", { name: "Close output" }).click();
    await expect(outputPanel(page)).toHaveAttribute("data-open", "false");
    expect(await noOverflow()).toBe(true);
  });

  test("reduced motion skips the width transition", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openApp(page, LAPTOP);

    await historyToggle(page).click();

    // Without a transition the panel is at full width at once.
    await expect.poll(async () => (await boxOf(historyPanel(page))).width, { timeout: 100 }).toBeCloseTo(
      HISTORY_WIDTH_PX,
      0,
    );
  });
});
