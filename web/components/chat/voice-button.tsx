"use client";

import { Mic, MicOff } from "lucide-react";
import { useCallback, useState, useEffect } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useVoiceRecorder } from "@/lib/stt/use-voice-recorder";
import type { VoiceRecorderOptions } from "@/lib/stt/voice-recorder";

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
  const [webSpeechSupported, setWebSpeechSupported] = useState(true);

  const handleStart = useCallback(async () => {
    await start();
  }, [start]);

  const handleStop = useCallback(async () => {
    const b = await stop();
    if (b) {
      onBlob(b);
    }
  }, [stop, onBlob]);

  // Check Web Speech API support on mount
  useEffect(() => {
    const supported = typeof window !== "undefined" &&
      ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);
    setWebSpeechSupported(supported);
  }, []);

  // Show error toast on permission deny (only when not recording, to avoid spam)
  if (error && !recording) {
    toast.error(
      error.message.includes("microphone")
        ? "Microphone access denied. You can still type."
        : "Voice input failed. You can still type.",
    );
  }

  // Hide button entirely if Web Speech API is not supported
  if (!webSpeechSupported || disabled) {
    return null;
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
            aria-label={recording ? "Stop recording" : "Start voice recording"}
            className="size-6.5 min-h-[44px] min-w-[44px]" // ≥44px touch target
          >
            {recording ? <MicOff size={14} strokeWidth={2.5} /> : <Mic size={14} strokeWidth={2.5} />}
          </Button>
        } />
        <TooltipContent>{recording ? "Stop recording" : "Start voice recording"}</TooltipContent>
      </Tooltip>
      {showAudioLevel && recording && audioLevel > 0 ? (
        <AudioLevelMeter level={audioLevel} />
      ) : null}
    </>
  );
}

/** Audio level meter: animated bars that reflect input volume. */
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
