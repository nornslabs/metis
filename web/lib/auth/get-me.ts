import "server-only";

import { cookies } from "next/headers";
import { cache } from "react";
import { z } from "zod";

import { API_ORIGIN } from "@/lib/api/origin";

const meSchema = z.object({
  id: z.string(),
  email: z.string(),
  name: z.string().nullable(),
  image: z.string().nullable(),
});

export type Me = z.infer<typeof meSchema>;

/**
 * The signed-in user, or null when there is no valid session.
 * Forwards the incoming cookie to `GET /v1/auth/me`. SHIP-222 replaces this with the typed client.
 */
export const getMe = cache(async (): Promise<Me | null> => {
  const cookieHeader = (await cookies()).toString();
  const response = await fetch(`${API_ORIGIN}/v1/auth/me`, {
    headers: cookieHeader ? { cookie: cookieHeader } : {},
    cache: "no-store",
  });
  if (response.status === 401) return null;
  if (!response.ok) {
    throw new Error(`GET /v1/auth/me failed with status ${response.status}`);
  }
  return meSchema.parse(await response.json());
});
