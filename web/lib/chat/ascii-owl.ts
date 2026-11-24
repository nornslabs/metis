/** The ASCII owl's grid: characters from dark to bright (ui-context.md, AsciiOwl). */
export const ASCII_RAMP = " .,:;-=+*#%@";
export const ASCII_COLS = 72;
export const ASCII_ROWS = 46;
/** Pixel size of one cell: characters are about twice as tall as wide. */
export const ASCII_CELL_WIDTH = 6;
export const ASCII_CELL_HEIGHT = 9;
/** Pixels are sampled every second row and column inside a cell. */
const SAMPLE_STEP = 2;
const CHANNELS = 4;
const CHANNEL_MAX = 255;

/** The ramp character for a brightness from 0 (dark) to 1 (bright); out-of-range values are clamped. */
export function rampChar(brightness: number): string {
  const last = ASCII_RAMP.length - 1;
  const index = Math.round(Math.min(1, Math.max(0, brightness)) * last);
  return ASCII_RAMP.charAt(index);
}

export interface PixelGrid {
  /** Width in pixels of the RGBA buffer. */
  width: number;
  cols: number;
  rows: number;
  cellWidth: number;
  cellHeight: number;
}

/**
 * Turns an RGBA buffer (the red channel is the brightness) into text: `rows` lines of `cols`
 * characters, trailing spaces trimmed, one newline after each line. Reads the buffer, never changes it.
 */
export function gridFromPixels(data: ArrayLike<number>, grid: PixelGrid): string {
  const { width, cols, rows, cellWidth, cellHeight } = grid;
  const samples = Math.ceil(cellHeight / SAMPLE_STEP) * Math.ceil(cellWidth / SAMPLE_STEP);
  const lines: string[] = [];
  for (let row = 0; row < rows; row += 1) {
    let line = "";
    for (let col = 0; col < cols; col += 1) {
      let sum = 0;
      for (let y = 0; y < cellHeight; y += SAMPLE_STEP) {
        for (let x = 0; x < cellWidth; x += SAMPLE_STEP) {
          sum += data[((row * cellHeight + y) * width + (col * cellWidth + x)) * CHANNELS] ?? 0;
        }
      }
      line += rampChar(sum / samples / CHANNEL_MAX);
    }
    lines.push(`${line.trimEnd()}\n`);
  }
  return lines.join("");
}
