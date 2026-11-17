import "server-only";

import { redirect } from "next/navigation";

import { signInHref } from "@/lib/auth/redirect";

import { isSessionError } from "./errors";

/** In a server component: a lost session redirects to `/sign-in` (back to `path` afterwards); any other error is rethrown. */
export function redirectIfSignedOut(error: unknown, path = "/"): never {
  if (isSessionError(error)) redirect(signInHref(path));
  throw error;
}
