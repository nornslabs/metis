import "server-only";

import { cache } from "react";

import { isSessionError } from "@/lib/api/errors";
import { bodyOf } from "@/lib/api/result";
import type { components } from "@/lib/api/schema";
import { getServerClient } from "@/lib/api/server-client";

export type Me = components["schemas"]["User"];

/** The signed-in user, or null when there is no valid session (`GET /v1/auth/me`). */
export const getMe = cache(async (): Promise<Me | null> => {
  const client = await getServerClient();
  try {
    return bodyOf(await client.GET("/v1/auth/me"));
  } catch (error) {
    if (isSessionError(error)) return null;
    throw error;
  }
});
