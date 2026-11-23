/** VoiceRecorder manages MediaRecorder lifecycle for voice input.
 *
 * Platform-agnostic: no React, no DOM assumptions beyond `navigator.mediaDevices`
 * and `MediaRecorder` globals. Returns a `Blob` (WebM/Opus) on stop.
 *
 * Options:
 * - `silenceTimeoutMs`: auto-stop after this many ms of no audio data (default: no auto-stop)
 * - `mimeType`: preferred MIME type for MediaRecorder (default: "audio/webm")
 */
export interface VoiceRecorderOptions {
  silenceTimeoutMs?: number;
  mimeType?: string;
}

export interface VoiceRecorderState {
  recording: boolean;
  error: Error | null;
  blob: Blob | null;
  audioLevel: number;
}

export class VoiceRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private mediaStream: MediaStream | null = null;
  private silenceTimer: ReturnType<typeof setTimeout> | null = null;
  private chunks: Blob[] = [];
  private resolveStop: ((blob: Blob | null) => void) | null = null;

  private _recording = false;
  private _error: Error | null = null;
  private _blob: Blob | null = null;
  private _audioLevel = 0;

  constructor(private options: VoiceRecorderOptions = {}) {}

  get state(): VoiceRecorderState {
    return {
      recording: this._recording,
      error: this._error,
      blob: this._blob,
      audioLevel: this._audioLevel,
    };
  }

  get recording() { return this._recording; }
  get error() { return this._error; }
  get blob() { return this._blob; }
  get audioLevel() { return this._audioLevel; }

  /** Start recording: request mic permission, create MediaRecorder, begin capturing. */
  async start(): Promise<void> {
    this._error = null;
    this._blob = null;
    this.chunks = [];
    this._audioLevel = 0;

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      this._error = err instanceof Error ? err : new Error(String(err));
      this._recording = false;
      return;
    }

    const mimeType = this.options.mimeType ?? "audio/webm";
    const options = MediaRecorder.isTypeSupported?.(mimeType) ? { mimeType } : undefined;

    this.mediaRecorder = new MediaRecorder(this.mediaStream, options);

    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        this.chunks.push(event.data);
        // Rough audio level from blob size (bigger chunk = louder)
        this._audioLevel = Math.min(event.data.size / 1000, 1);
        this._scheduleSilenceReset();
      }
    };

    this.mediaRecorder.onstop = () => {
      this._finalizeRecording();
    };

    this.mediaRecorder.onerror = () => {
      this._error = new Error("MediaRecorder error");
      this._recording = false;
      this._cleanup();
    };

    this.mediaRecorder.start();
    this._recording = true;
  }

  /** Stop recording: finalize, release mic tracks, return the captured Blob. */
  async stop(): Promise<Blob | null> {
    if (!this._recording || !this.mediaRecorder) {
      return this._blob;
    }

    return new Promise((resolve) => {
      this.resolveStop = resolve;
      this.mediaRecorder!.stop();
    });
  }

  private _scheduleSilenceReset() {
    if (this.silenceTimer) clearTimeout(this.silenceTimer);
    if (this.options.silenceTimeoutMs) {
      this.silenceTimer = setTimeout(() => {
        this._audioLevel = 0;
        // Auto-stop: silence timeout reached, stop recording
        if (this._recording && this.mediaRecorder) {
          this.mediaRecorder.stop();
        }
      }, this.options.silenceTimeoutMs);
    }
  }

  private async _finalizeRecording() {
    this._recording = false;
    this._cleanup();

    const blob = this.chunks.length > 0
      ? new Blob(this.chunks, { type: "audio/webm" })
      : null;
    this._blob = blob;

    if (this.resolveStop) {
      const cb = this.resolveStop;
      this.resolveStop = null;
      cb(blob);
    }
  }

  private _cleanup() {
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    this.mediaStream?.getTracks().forEach((track) => track.stop());
    this.mediaStream = null;
    this.mediaRecorder = null;
  }
}
