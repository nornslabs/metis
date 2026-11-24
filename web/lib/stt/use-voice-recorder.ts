"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { VoiceRecorder, type VoiceRecorderOptions } from "@/lib/stt/voice-recorder";

const DEFAULT_OPTIONS: VoiceRecorderOptions = {};

export function useVoiceRecorder(options: VoiceRecorderOptions = DEFAULT_OPTIONS) {
  const [recording, setRecording] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [audioLevel, setAudioLevel] = useState<number>(0);

  const optionsRef = useRef<VoiceRecorderOptions>(options);
  const recorderRef = useRef<VoiceRecorder | null>(null);
  const rafRef = useRef<number | null>(null);

  const getRecorder = useCallback((): VoiceRecorder => {
    if (recorderRef.current === null) {
      recorderRef.current = new VoiceRecorder(optionsRef.current);
    }
    return recorderRef.current;
  }, []);

  useEffect(() => {
    if (!recording) {
      return;
    }
    const recorder = getRecorder();
    const poll = (): void => {
      setAudioLevel(recorder.audioLevel);
      rafRef.current = requestAnimationFrame(poll);
    };
    rafRef.current = requestAnimationFrame(poll);
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, [recording, getRecorder]);

  useEffect(() => {
    return () => {
      void recorderRef.current?.stop();
    };
  }, []);

  const start = useCallback(async (): Promise<void> => {
    const recorder = getRecorder();
    setError(null);
    setBlob(null);
    await recorder.start();
    setRecording(recorder.recording);
    setError(recorder.error);
  }, [getRecorder]);

  const stop = useCallback(async (): Promise<Blob | null> => {
    const recorder = getRecorder();
    const stopped = await recorder.stop();
    setRecording(recorder.recording);
    setAudioLevel(0);
    setBlob(stopped);
    return stopped;
  }, [getRecorder]);

  return {
    recording,
    error,
    blob,
    audioLevel,
    start,
    stop,
  };
}