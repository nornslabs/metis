"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { VoiceRecorder, type VoiceRecorderOptions } from "@/lib/stt/voice-recorder";

/** Hook wrapping VoiceRecorder in React state. Exposes recording state and start/stop. */
export function useVoiceRecorder(options: VoiceRecorderOptions = {}) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);

  // Create VoiceRecorder once via useMemo (avoids ref access during render)
  const recorder = useMemo(() => new VoiceRecorder(options), [options]);

  // Poll audio level while recording (runs in requestAnimationFrame)
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (recorder.recording) {
      const poll = () => {
        if (recorder.recording) {
          setAudioLevel(recorder.audioLevel);
          rafRef.current = requestAnimationFrame(poll);
        }
      };
      rafRef.current = requestAnimationFrame(poll);
    } else {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    }
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [recorder.recording, recorder]);

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

  return {
    recording,
    error,
    blob,
    audioLevel,
    start,
    stop,
  };
}