"use client";

import { useCallback } from "react";
import { toast } from "sonner";

import { getSTTClientConfig, getSTTClientProvider } from "./config";
import type { STTProvider } from "./types";

/** Hook for STT transcription that routes to the correct provider (server or client). */
export function useSTTTranscription() {
  const { provider } = getSTTClientConfig();

  const transcribe = useCallback(
    async (blob: Blob): Promise<string | null> => {
      if (provider === "sarvam") {
        // Use server endpoint for Sarvam
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
            if (response.status === 400 && error.error === "key_not_configured") {
              toast.error("Add your Sarvam API key in Settings to use Sarvam STT");
            } else if (response.status === 400 && error.error === "client_side_provider") {
              toast.error("Use client-side Web Speech API for this provider");
            } else {
              toast.error(error.detail || "Transcription failed. You can still type.");
            }
            return null;
          }

          const data = await response.json();
          return data.transcript ?? null;
        } catch {
          toast.error("Transcription failed. You can still type.");
          return null;
        }
      }

      // Use client-side provider for web-speech and mock
      try {
        const clientProvider: STTProvider = getSTTClientProvider(provider);
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
    [provider],
  );

  return { transcribe, provider };
}