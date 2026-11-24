"use client";

import { useCallback } from "react";
import { toast } from "sonner";

import type { STTProvider } from "./types";

/** Hook for STT transcription that routes to the correct provider (server or client). */
export function useSTTTranscription() {
  const transcribe = useCallback(
    async (blob: Blob): Promise<string | null> => {
      // Always try server endpoint first (handles Sarvam if key exists)
      try {
        const formData = new FormData();
        formData.append("file", blob, "audio.webm");

        const response = await fetch("/v1/stt/transcribe", {
          method: "POST",
          headers: {
            "X-Metis-Client": "web",
          },
          body: formData,
          credentials: "include",
        });

        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          // Server says use client-side Web Speech API
          if (response.status === 400 && error.error === "client_side_provider") {
            // Fall through to client-side provider
          } else if (response.status === 400 && error.error === "key_not_configured") {
            toast.error("Add your Sarvam API key in Settings to use Sarvam STT");
            return null;
          } else {
            toast.error(error.detail || "Transcription failed. You can still type.");
            return null;
          }
        } else {
          const data = await response.json();
          return data.transcript ?? null;
        }
      } catch {
        // Network error, fall through to client-side
      }

      // Use client-side Web Speech API provider
      try {
        const { getSTTClientProvider } = await import("./config");
        const clientProvider: STTProvider = getSTTClientProvider();
        const transcript = await clientProvider.transcribe(blob);
        if (!transcript || !transcript.trim()) {
          toast.error("Nothing heard. Try again.");
          return null;
        }
        return transcript;
      } catch (error) {
        const message = error instanceof Error ? error.message : "Transcription failed";
        toast.error(`${message}. You can still type.`);
        return null;
      }
    },
    [],
  );

  return { transcribe };
}