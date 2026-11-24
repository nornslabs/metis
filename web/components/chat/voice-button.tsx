"use client";

import { Mic, MicOff } from "lucide-react";
import { useCallback, useState, useEffect, useRef } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useVoiceRecorder } from "@/lib/stt/use-voice-recorder";
import type { VoiceRecorderOptions } from "@/lib/stt/voice-recorder";

// UI strings extracted for i18n readiness
const VOICE_STRINGS = {
  startRecording: "Start voice recording",
  stopRecording: "Stop recording",
  micDenied: "Microphone access denied. You can still type.",
  transcriptionFailed: "Voice input failed. You can still type.",
  nothingHeard: "Nothing heard. Try again.",
  notSupported: "Voice input not supported in this browser",
} as const;

interface VoiceButtonProps {
  /** Called when recording stops with the captured audio blob. */
  onBlob: (blob: Blob) => void;
  /** Options passed to VoiceRecorder. */
  options?: VoiceRecorderOptions;
  /** Whether voice input is currently disabled (e.g. browser doesn't support it). */
  disabled?: boolean;
  /** Show audio level meter while recording. */
  showAudioLevel?: boolean;
}

export function VoiceButton({ onBlob, options, disabled = false, showAudioLevel = false }: VoiceButtonProps) {
  const { recording, error, audioLevel, start, stop } = useVoiceRecorder(options);

  // Initialize with correct value (not in useEffect)
  const [webSpeechSupported] = useState(() => {
    if (typeof window === "undefined") return false;
    return "SpeechRecognition" in window || "webkitSpeechRecognition" in window;
  });

  const errorToastedRef = useRef(false);

  const handleStart = useCallback(async () => {
    try {
      await start();
    } catch {
      // start() sets error internally; handled by the error toast effect
    }
  }, [start]);

  const handleStop = useCallback(async () => {
    const b = await stop();
    if (b) {
      onBlob(b);
    }
  }, [stop, onBlob]);

  // Show error toast on permission deny (only once per error, not on every render)
  useEffect(() => {
    if (error && !recording && !errorToastedRef.current) {
      toast.error(
        error.message.includes("microphone")
          ? VOICE_STRINGS.micDenied
          : VOICE_STRINGS.transcriptionFailed,
      );
      errorToastedRef.current = true;
    } else if (!error) {
      errorToastedRef.current = false;
    }
  }, [error, recording]);

  // Show button with tooltip when Web Speech API not supported
  if (!webSpeechSupported || disabled) {
    return (
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                type="button"
                variant="outline"
                size="icon-xs"
                disabled
                aria-label={VOICE_STRINGS.notSupported}
                className="size-6.5 opacity-50"
              />
            }
          >
            <MicOff size={14} strokeWidth={2} />
          </TooltipTrigger>
          <TooltipContent>{VOICE_STRINGS.notSupported}</TooltipContent>
        </Tooltip>
      );
  }

  return (
    <>
      <Tooltip>
        <TooltipTrigger render={
          <Button
            type="button"
            variant={recording ? "destructive" : "default"}
            size="icon-xs"
            onClick={recording ? handleStop : handleStart}
            disabled={!recording && error !== null}
            aria-label={recording ? VOICE_STRINGS.stopRecording : VOICE_STRINGS.startRecording}
            className="size-6.5"
          >
            {recording ? <MicOff size={14} strokeWidth={2.5} /> : <Mic size={14} strokeWidth={2.5} />}
          </Button>
        } />
        <TooltipContent>{recording ? VOICE_STRINGS.stopRecording : VOICE_STRINGS.startRecording}</TooltipContent>
      </Tooltip>
      {showAudioLevel && recording && audioLevel > 0 ? (
        <AudioLevelMeter level={audioLevel} />
      ) : null}
    </>
  );
}

/** Audio level meter: animated bars that reflect real mic input volume via AnalyserNode. */
export function AudioLevelMeter({ level }: { level: number }) {
  const bars = Array.from({ length: 5 }, (_, i) => i);
  const height = Math.min(level * 100, 1);
  return (
    <div className="flex items-end gap-1 h-4">
      {bars.map((i) => (
        <div
          key={i}
          className={`w-1.5 bg-primary rounded-sm transition-all duration-100 ${
            height > i / 5 ? "bg-primary" : "bg-muted"
          }`}
          style={{ height: `${Math.max(height * 20, 20)}%` }}
        />
      ))}
    </div>
  );
}