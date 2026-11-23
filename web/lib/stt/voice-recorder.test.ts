import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import { VoiceRecorder } from "./voice-recorder";

const originalMediaDevices = navigator.mediaDevices as MediaDevices | undefined;

function createMockRecorder() {
  return {
    start: vi.fn(),
    stop: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    state: "inactive",
    ondataavailable: null as ((event: { data: Blob }) => void) | null,
    onstop: null as (() => void) | null,
    onerror: null as (() => void) | null,
    error: null as Error | null,
  };
}

class MockMediaRecorderClass {
  start = vi.fn();
  stop = vi.fn();
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
  state = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  error: Error | null = null;

  constructor(_stream: MediaStream, _options?: MediaRecorderOptions) {}
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.useFakeTimers();
  vi.stubGlobal("MediaRecorder", MockMediaRecorderClass);
});

afterEach(() => {
  if (originalMediaDevices) {
    Object.defineProperty(navigator, "mediaDevices", { value: originalMediaDevices, configurable: true });
  }
  vi.useRealTimers();
});

function mockMediaDevices(override: Partial<MediaDevices> = {}) {
  const mockTrack = { stop: vi.fn() } as unknown as MediaStreamTrack;
  const mockStream = {
    getTracks: vi.fn(() => [mockTrack]),
  } as unknown as MediaStream;

  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: vi.fn(async () => mockStream), ...override },
    configurable: true,
  });

  return { stream: mockStream, track: mockTrack };
}

type VoiceRecorderInternals = {
  mediaRecorder: MediaRecorder | null;
};

describe("VoiceRecorder", () => {
  it("starts idle with no error", () => {
    const recorder = new VoiceRecorder();
    expect(recorder.recording).toBe(false);
    expect(recorder.error).toBeNull();
    expect(recorder.blob).toBeNull();
  });

  it("requests mic permission and starts recording on start()", async () => {
    mockMediaDevices();
    const voiceRecorder = new VoiceRecorder();

    await voiceRecorder.start();

    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(voiceRecorder.recording).toBe(true);
    expect(voiceRecorder.error).toBeNull();
  });

  it("stops recording and returns a Blob on stop()", async () => {
    mockMediaDevices();
    const voiceRecorder = new VoiceRecorder();

    await voiceRecorder.start();

    const fakeBlob = new Blob(["audio"], { type: "audio/webm" });
    const internals = voiceRecorder as unknown as VoiceRecorderInternals;
    internals.mediaRecorder?.ondataavailable?.({ data: fakeBlob } as unknown as BlobEvent);
    internals.mediaRecorder?.onstop?.(null as unknown as Event);

    const blob = await voiceRecorder.stop();

    expect(voiceRecorder.recording).toBe(false);
    expect(blob).not.toBeNull();
    expect(blob!.type).toBe("audio/webm");
  });

  it("sets error when getUserMedia is denied", async () => {
    mockMediaDevices({ getUserMedia: vi.fn(async () => { throw new Error("NotAllowedError: microphone access denied"); }) });
    const voiceRecorder = new VoiceRecorder();

    await voiceRecorder.start();

    expect(voiceRecorder.recording).toBe(false);
    expect(voiceRecorder.error).toBeTruthy();
    expect(voiceRecorder.error!.message).toContain("microphone");
  });

  it("auto-stops on silence after configurable ms", async () => {
    mockMediaDevices();
    const voiceRecorder = new VoiceRecorder({ silenceTimeoutMs: 100 });

    await voiceRecorder.start();

    vi.advanceTimersByTime(150);
    // Silence timer fired mediaRecorder.stop(); simulate browser firing onstop
    const internals = voiceRecorder as unknown as VoiceRecorderInternals;
    internals.mediaRecorder?.onstop?.(null as unknown as Event);

    expect(voiceRecorder.recording).toBe(false);
  });

  it("releases mic tracks on stop", async () => {
    const { stream, track } = mockMediaDevices();
    const voiceRecorder = new VoiceRecorder();

    await voiceRecorder.start();

    const fakeBlob = new Blob(["audio"], { type: "audio/webm" });
    const internals = voiceRecorder as unknown as VoiceRecorderInternals;
    internals.mediaRecorder?.ondataavailable?.({ data: fakeBlob } as unknown as BlobEvent);
    internals.mediaRecorder?.onstop?.(null as unknown as Event);

    await voiceRecorder.stop();

    expect(track.stop).toHaveBeenCalled();
  });
});
