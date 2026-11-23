import {
  ASCII_CELL_HEIGHT,
  ASCII_CELL_WIDTH,
  ASCII_COLS,
  ASCII_ROWS,
  gridFromPixels,
} from "./ascii-owl";
import { OWL_FACE_PATH } from "@/lib/brand/owl-path";

/** The two pictures of the ASCII owl: eyes open, and eyes shut for the blink. */
export interface OwlFrames {
  open: string;
  shut: string;
}

const EYE_CENTERS = [8.5, 15.5] as const;
const EYE_Y = 11;
const CHEVRONS: ReadonlyArray<readonly [number, number]> = [
  [7, 16],
  [12, 19.2],
  [17, 16],
  [9.5, 18],
  [14.5, 18],
];
// Grey levels: the canvas is only read back as brightness.
const BLACK = "#000";
const WHITE = "#fff";
const RING = "#cfcfcf";
const LID = "#8a8a8a";
const LASH = "#111";
const CHEVRON = "#3a3a3a";
const FACE_STOPS: ReadonlyArray<readonly [number, string]> = [
  [0, "#f2f2f2"],
  [0.6, "#a8a8a8"],
  [1, "#5a5a5a"],
];
// The drawing's size in owl-path units, and where its centre sits.
const FIT_WIDTH = 18.5;
const FIT_HEIGHT = 20.5;
const CENTER_X = 12;
const CENTER_Y = 12.2;

function drawOwl(context: CanvasRenderingContext2D, width: number, height: number, shut: boolean): void {
  context.fillStyle = BLACK;
  context.fillRect(0, 0, width, height);
  const scale = Math.min(width / FIT_WIDTH, height / FIT_HEIGHT);
  context.translate(width / 2 - CENTER_X * scale, height / 2 - CENTER_Y * scale);
  context.scale(scale, scale);

  const shading = context.createRadialGradient(12, 9, 1, 12, 12, 12);
  for (const [offset, color] of FACE_STOPS) shading.addColorStop(offset, color);
  context.fillStyle = shading;
  context.fill(new Path2D(OWL_FACE_PATH), "evenodd");

  context.strokeStyle = CHEVRON;
  context.lineWidth = 0.45;
  for (const [x, y] of CHEVRONS) {
    context.beginPath();
    context.moveTo(x - 1, y - 0.7);
    context.lineTo(x, y);
    context.lineTo(x + 1, y - 0.7);
    context.stroke();
  }

  context.strokeStyle = RING;
  context.lineWidth = 0.5;
  for (const x of EYE_CENTERS) {
    context.beginPath();
    context.arc(x, EYE_Y, 3.9, 0, Math.PI * 2);
    context.stroke();
  }

  if (!shut) {
    context.fillStyle = WHITE;
    for (const x of EYE_CENTERS) {
      context.beginPath();
      context.arc(x, EYE_Y, 1.35, 0, Math.PI * 2);
      context.fill();
    }
    return;
  }
  context.fillStyle = LID;
  for (const x of EYE_CENTERS) {
    context.beginPath();
    context.arc(x, EYE_Y, 3.25, 0, Math.PI * 2);
    context.fill();
  }
  context.strokeStyle = LASH;
  context.lineWidth = 0.6;
  for (const x of EYE_CENTERS) {
    context.beginPath();
    context.moveTo(x - 2.6, EYE_Y);
    context.quadraticCurveTo(x, EYE_Y + 1.4, x + 2.6, EYE_Y);
    context.stroke();
  }
}

function rasterise(shut: boolean): string | null {
  const width = ASCII_COLS * ASCII_CELL_WIDTH;
  const height = ASCII_ROWS * ASCII_CELL_HEIGHT;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  drawOwl(context, width, height, shut);
  const { data } = context.getImageData(0, 0, width, height);
  return gridFromPixels(data, {
    width,
    cols: ASCII_COLS,
    rows: ASCII_ROWS,
    cellWidth: ASCII_CELL_WIDTH,
    cellHeight: ASCII_CELL_HEIGHT,
  });
}

let cached: OwlFrames | null | undefined;

/** Both frames, drawn once per page load; null when the browser has no canvas 2D context. Client only. */
export function owlFrames(): OwlFrames | null {
  if (cached !== undefined) return cached;
  const open = rasterise(false);
  const shut = rasterise(true);
  cached = open !== null && shut !== null ? { open, shut } : null;
  return cached;
}
