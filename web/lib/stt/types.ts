export interface STTProvider {
  transcribe(audioBlob: Blob): Promise<string>;
}

export type STTProviderName = "sarvam" | "web-speech" | "mock";
