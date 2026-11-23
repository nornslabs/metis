"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { VoiceRecorder, type VoiceRecorderOptions } from "@/lib/stt/voice-recorder";

/** Hook wrapping VoiceRecorder in React state. Exposes recording state and start/stop. */
export function useVoiceRecorder(options: VoiceRecorderOptions = {}) {
  const recorderRef = useRef<VoiceRecorder | null>(null);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);

  // Lazy init: create VoiceRecorder once (idempotent, runs on first render only)
  if (!recorderRef.current) {
    recorderRef.current = new VoiceRecorder(options);
  }
  const recorder = recorderRef.current;

  const start = useCallback(async () => {
    setError(null);
    setBlob(null);
    await recorder.start();
    setRecording(recorder.recording);
    setError(recorder.error);
  }, [recorder]);

  const stop = useCallback(async (): Promise<Blob | null> => {
    const b = await recorder.stop();
    setRecording(recorder.recording);
    setBlob(recorder.blob);
    return b;
  }, [recorder]);

  // Poll audio level while recording (runs in requestAnimationFrame)
  const rafRef = useRef<number | null>(null);
  const poll = useCallback(() => {
    if (recorder.recording) {
      setAudioLevel(recorder.audioLevel);
      rafRef.current = requestAnimationFrame(poll);
    }
  }, [recorder.recording, recorder.audioLevel]);

  useEffect(() => {
    if (recorder.recording) {
      rafRef.current = requestAnimationFrame(poll);
    } else {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    }
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [recorder.recording, poll]);

  return {
    recording,
    error,
    blob,
    audioLevel,
    start,
    stop,
  };
}
