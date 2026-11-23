"use client";

import { useState } from "react";

import { isLocked, type SpecEditor, type SpecEditorState } from "@/lib/spec/spec-editor";

/** Why Confirm is off for this state, or null when it can be used. */
export function confirmBlockedReason(state: SpecEditorState): string | null {
  if (state.latest === null || isLocked(state)) return "There is no draft to confirm";
  if (state.view.mode !== "edit") return `Back to v${state.latest.number} to confirm`;
  if (state.status === "dirty" || state.status === "saving") return "Waiting for your last change to save";
  if (state.status === "conflict") return "Reload the newest version first";
  if (state.confirming) return "Confirming";
  return null;
}

/** What the Confirm button does for this state; shared by the pane footer and the chat prompt. */
export function useConfirmSpec(editor: SpecEditor, state: SpecEditorState) {
  const [open, setOpen] = useState(false);
  return { open, setOpen, blockedReason: confirmBlockedReason(state), confirm: () => void editor.confirm() };
}
