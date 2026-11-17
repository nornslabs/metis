import "server-only";

import { z } from "zod";

import { API_ORIGIN } from "@/lib/api/origin";

const providersSchema = z.array(z.string());

/** Provider names the server offers (`["google"]`), or null when the server cannot be reached. */
export async function getProviders(): Promise<readonly string[] | null> {
  try {
    const response = await fetch(`${API_ORIGIN}/v1/auth/providers`, {
      cache: "no-store",
    });
    if (!response.ok) return null;
    return providersSchema.parse(await response.json());
  } catch {
    return null;
  }
}
