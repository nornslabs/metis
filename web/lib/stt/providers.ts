import type { STTProvider } from "./types";

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognition;
    webkitSpeechRecognition?: new () => SpeechRecognition;
  }
}

interface SpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  onresult: (event: { results: { [index: number]: { [index: number]: { transcript: string } } } }) => void;
  onerror: (event: { error: string }) => void;
  onend: () => void;
  start(): void;
}

/** Sarvam STT provider. POSTs audio to Sarvam's speech-to-text API. */
export class SarvamSTTProvider implements STTProvider {
  constructor(private apiKey: string) {}

  async transcribe(audioBlob: Blob): Promise<string> {
    const formData = new FormData();
    formData.append("file", audioBlob, "audio.webm");

    const response = await fetch("https://api.sarvam.ai/speech-to-text", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Sarvam STT failed: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    return data.transcript ?? "";
  }
}

/** Browser Web Speech API provider. Uses window.SpeechRecognition natively. */
export class WebSpeechSTTProvider implements STTProvider {
  async transcribe(_audioBlob: Blob): Promise<string> {
    // Check window once (SSR-safe), then look for either SpeechRecognition variant
    const SpeechRecognition =
      typeof window !== "undefined" &&
      (window.SpeechRecognition || window.webkitSpeechRecognition);

    if (!SpeechRecognition) {
      throw new Error("Web Speech API is not available in this browser");
    }

    return new Promise((resolve, reject) => {
      const recognition = new SpeechRecognition();

      recognition.continuous = false;
      recognition.interimResults = false;

      let resolved = false;

      recognition.onresult = (event: { results: { [index: number]: { [index: number]: { transcript: string } } } }) => {
        resolved = true;
        const transcript = event.results[0][0].transcript;
        resolve(transcript);
      };

      recognition.onerror = (event: { error: string }) => {
        if (!resolved) {
          resolved = true;
          reject(new Error(`Web Speech API error: ${event.error}`));
        }
      };

      recognition.onend = () => {
        if (!resolved) {
          resolved = true;
          resolve("");
        }
      };

      recognition.start();
    });
  }
}
