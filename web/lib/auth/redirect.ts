import { firstParam } from "@/lib/search-params";

export const DEFAULT_REDIRECT = "/";
export const SIGN_IN_PATH = "/sign-in";

const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;

function isSafeRelativePath(value: string): boolean {
  if (!value.startsWith("/")) return false;
  if (value.startsWith("//") || value.startsWith("/\\")) return false;
  if (CONTROL_CHARS.test(value)) return false;
  if (value === SIGN_IN_PATH || value.startsWith(`${SIGN_IN_PATH}?`)) {
    return false;
  }
  return true;
}

/** Returns the path to go to after sign-in; anything not a plain relative path becomes `/`. */
export function safeRedirectPath(
  value: string | readonly string[] | undefined,
): string {
  const first = firstParam(value);
  if (typeof first !== "string" || first === "") return DEFAULT_REDIRECT;
  return isSafeRelativePath(first) ? first : DEFAULT_REDIRECT;
}

/** The sign-in URL that returns the user to `path` afterwards. */
export function signInHref(path: string): string {
  const target = safeRedirectPath(path);
  if (target === DEFAULT_REDIRECT) return SIGN_IN_PATH;
  return `${SIGN_IN_PATH}?redirect_to=${encodeURIComponent(target)}`;
}
