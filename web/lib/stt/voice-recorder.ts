/** VoiceRecorder manages MediaRecorder lifecycle for voice input.
 *
 * Platform-agnostic: no React, no DOM assumptions beyond `navigator.mediaDevices`,
 * `MediaRecorder`, and `AudioContext` globals. Returns a `Blob` (WebM/Opus) on stop.
 *
 * Options:
 * - `silenceTimeoutMs`: auto-stop after this many ms of no audio data (default: no auto-stop)
 * - `mimeType`: preferred MIME type for MediaRecorder (default: "audio/webm")
 */
declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}

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
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private silenceTimer: ReturnType<typeof setTimeout> | null = null;
  private rafId: ReturnType<typeof requestAnimationFrame> | null = null;
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

  /** Start recording: request mic permission, create MediaRecorder + AnalyserNode, begin capturing. */
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

    // Build an AnalyserNode for real-time audio levels
    try {
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
      if (this.audioContext.state === "suspended") {
        await this.audioContext.resume();
      }
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 2048;
      const source = this.audioContext.createMediaStreamSource(this.mediaStream);
      source.connect(this.analyser);
    } catch {
      // Analyser is optional — audio level meter will show 0 if unavailable
      this.audioContext = null;
      this.analyser = null;
    }

    const mimeType = this.options.mimeType ?? "audio/webm";
    const options = MediaRecorder.isTypeSupported?.(mimeType) ? { mimeType } : undefined;

    this.mediaRecorder = new MediaRecorder(this.mediaStream, options);

    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        this.chunks.push(event.data);
        this._scheduleSilenceReset();
      }
    };

    this.mediaRecorder.onstop = () => {
      this._finalizeRecording();
    };

    this.mediaRecorder.onerror = (_event) => {
      this._error = new Error("MediaRecorder error");
      this._recording = false;
      this._cleanup();
    };

    this.mediaRecorder.start();
    this._recording = true;
    this._startLevelPolling();
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

  private _startLevelPolling() {
    if (!this.analyser || !this.audioContext) return;
    const data = new Uint8Array(this.analyser.frequencyBinCount);
    const poll = () => {
      if (!this._recording) return;
      this.analyser!.getByteFrequencyData(data);
      // Average volume from frequency data (0-255), normalized to 0-1
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        sum += data[i];
      }
      const avg = sum / data.length / 255;
      this._audioLevel = Math.round(avg * 100) / 100;
      this.rafId = requestAnimationFrame(poll);
    };
    poll();
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
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    this.analyser = null;
    this.mediaStream?.getTracks().forEach((track) => track.stop());
    this.mediaStream = null;
    this.mediaRecorder = null;
  }
}