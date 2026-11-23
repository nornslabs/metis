import { expect, test, type Page } from "@playwright/test";

import { SESSION_COOKIE, createSessionToken } from "./support/session";
import { crossesTick, tickCentres } from "./support/ticks";

const MUTATION_HEADERS = { "X-Metis-Client": "web" };
const VIEWPORTS = [
  { name: "1920", width: 1920, height: 1000 },
  { name: "1440", width: 1440, height: 900 },
  { name: "375", width: 375, height: 800 },
] as const;
const COLUMN_WIDTH_PX = 760;
const WIDE = { width: 1440, height: 900 };
const NARROW_DESKTOP = { width: 1100, height: 800 };
const BELOW_GUIDES = { width: 800, height: 800 };
const PHONE = { width: 375, height: 800 };
const WIDE_TICK_COUNT = 12; // 4 verticals × (header line, footer line, input band)
const FRAME_ONLY_TICK_COUNT = 6; // 2 verticals × 3 lines

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: SESSION_COOKIE, value: createSessionToken(), url: baseURL!, httpOnly: true, sameSite: "Lax" },
  ]);
  await context.request.get("/v1/workspaces/current");
});

async function createIdea(page: Page, title: string): Promise<string> {
  const response = await page.request.post("/v1/ideas", {
    headers: MUTATION_HEADERS,
    data: { title, raw_text: `${title}\nA longer description of the idea for the frame test.` },
  });
  expect(response.status()).toBe(201);
  return (await response.json()).id;
}

async function lineEdges(page: Page) {
  return page.evaluate(() => {
    const rectOf = (part: string) => document.querySelector(`[data-frame="${part}"]`)?.getBoundingClientRect();
    const safe = rectOf("safe")!;
    const column = rectOf("column")!;
    return {
      frameXs: [safe.left, safe.right],
      guideXs: [column.left, column.right],
      headerY: rectOf("header")!.bottom,
      footerY: rectOf("footer")!.top,
      bandY: rectOf("band")?.top ?? null,
    };
  });
}

test.describe("frame", () => {
  test("header shows only the brand on the empty page", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Metis", { exact: true })).toBeVisible();
    await expect(page.getByText("Stage:")).toHaveCount(0);
  });

  test("header crumb shows the idea title and its stage", async ({ page }) => {
    const title = `Frame crumb ${Date.now()}`;
    const id = await createIdea(page, title);
    await page.goto(`/ideas/${id}`);
    const header = page.locator("header");
    await expect(header.getByText(title)).toBeVisible();
    await expect(header.getByLabel(/^Stage: /)).toBeVisible();
  });

  test("the owl is decorative and its animations respect reduced motion", async ({ page }) => {
    await page.goto("/");
    const owl = page.locator("header svg.owl");
    await expect(owl).toHaveAttribute("aria-hidden", "true");
    const countAnimations = () =>
      owl.evaluate((svg) => {
        svg.setAttribute("data-state", "working");
        return svg.getAnimations({ subtree: true }).filter((a) => a instanceof CSSAnimation).length;
      });

    await page.emulateMedia({ reducedMotion: "no-preference" });
    expect(await countAnimations()).toBeGreaterThan(0);
    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(await countAnimations()).toBe(0);
  });

  for (const viewport of VIEWPORTS) {
    test(`no horizontal scroll at ${viewport.name}px`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto("/");
      await expect(page.getByLabel("Your idea")).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }

  test("ticks sit on the crossings, follow a resize and ignore the theme", async ({ page }) => {
    await page.setViewportSize(WIDE);
    await page.goto("/");
    await expect(page.getByTestId("frame-tick")).toHaveCount(WIDE_TICK_COUNT);

    // The column is 760px, centred: its guides are independent of anything the page measures.
    const ticksAtWide = await tickCentres(page);
    const columnLeft = (WIDE.width - COLUMN_WIDTH_PX) / 2;
    expect(crossesTick(ticksAtWide, columnLeft, (await lineEdges(page)).headerY)).toBe(true);

    for (const size of [WIDE, NARROW_DESKTOP, WIDE]) {
      await page.setViewportSize(size);
      await expect(page.getByTestId("frame-tick")).toHaveCount(WIDE_TICK_COUNT);
      const edges = await lineEdges(page);
      const ticks = await tickCentres(page);
      const ys = [edges.headerY, edges.footerY, edges.bandY!];
      for (const x of [...edges.frameXs, ...edges.guideXs]) {
        for (const y of ys) expect(crossesTick(ticks, x, y)).toBe(true);
      }
    }

    await page.evaluate(() => document.documentElement.classList.add("dark"));
    expect(await tickCentres(page)).toEqual(ticksAtWide);
  });

  test("hides the guides under 820px and every tick under 700px", async ({ page }) => {
    await page.goto("/");
    await page.setViewportSize(BELOW_GUIDES);
    await expect(page.getByTestId("frame-tick")).toHaveCount(FRAME_ONLY_TICK_COUNT);
    await page.setViewportSize(PHONE);
    await expect(page.getByTestId("frame-tick")).toHaveCount(0);
  });
});
