import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/* Apple-style spacing helpers */
export const spacing = {
  1: "var(--space-1)",
  2: "var(--space-2)",
  3: "var(--space-3)",
  4: "var(--space-4)",
  5: "var(--space-5)",
  6: "var(--space-6)",
  8: "var(--space-8)",
  10: "var(--space-10)",
  12: "var(--space-12)",
} as const;

/* Apple-style typography helpers */
export const typography = {
  largeTitle: "text-large-title",
  title1: "text-title-1",
  title2: "text-title-2",
  title3: "text-title-3",
  headline: "text-headline",
  body: "text-body",
  bodyStrong: "text-body-strong",
  callout: "text-callout",
  subhead: "text-subhead",
  footnote: "text-footnote",
  caption1: "text-caption-1",
  caption2: "text-caption-2",
} as const;

/* Apple-style shadow helpers */
export const shadows = {
  xs: "shadow-xs",
  sm: "shadow-sm",
  md: "shadow-md",
  lg: "shadow-lg",
} as const;

/* Apple-style radius helpers */
export const radius = {
  sm: "rounded-sm",
  md: "rounded-md",
  lg: "rounded-lg",
  full: "rounded-full",
} as const;

/* Apple-style transition helpers */
export const transitions = {
  fast: "transition-fast",
  normal: "transition-normal",
  slow: "transition-slow",
} as const;