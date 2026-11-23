import type { Page } from "@playwright/test";

export const TICK_TOLERANCE_PX = 1;

/** Page-space centres of every `+` tick. */
export async function tickCentres(page: Page): Promise<{ x: number; y: number }[]> {
  return page.getByTestId("frame-tick").evaluateAll((ticks) =>
    ticks.map((tick) => {
      const rect = tick.getBoundingClientRect();
      return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    }),
  );
}

export function crossesTick(ticks: readonly { x: number; y: number }[], x: number, y: number): boolean {
  return ticks.some((t) => Math.abs(t.x - x) <= TICK_TOLERANCE_PX && Math.abs(t.y - y) <= TICK_TOLERANCE_PX);
}
