import { z } from "zod";

import type { STTProviderName } from "./types";

const sttServerConfigSchema = z
  .object({
    provider: z.enum(["sarvam", "web-speech", "mock"] as const).default("web-speech"),
    sarvamApiKey: z.string().min(1).optional(),
  })
  .refine(
    (data) => data.provider !== "sarvam" || !!data.sarvamApiKey,
    {
      message: "SARVAM_API_KEY is required when STT_PROVIDER=sarvam",
      path: ["sarvamApiKey"],
    },
  );

export type STTServerConfig = z.infer<typeof sttServerConfigSchema>;

/** Validates STT env vars on the server. Throws if config is invalid. */
export function getSTTServerConfig(): STTServerConfig {
  return sttServerConfigSchema.parse({
    provider: process.env.STT_PROVIDER,
    sarvamApiKey: process.env.SARVAM_API_KEY,
  });
}
