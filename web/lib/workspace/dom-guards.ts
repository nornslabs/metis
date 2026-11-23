/** True when a key press happened while typing in a field, so shortcuts must leave it alone. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return target.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])") !== null;
}

/** True while a dialog or menu is open: it owns Esc, so panels must not react to it. */
export function hasOpenOverlay(root: ParentNode = document): boolean {
  return root.querySelector("[role='dialog'], [role='alertdialog'], [role='menu'], [role='listbox']") !== null;
}
