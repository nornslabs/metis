import { Info, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { KEYS_SETTINGS_HREF, llmBlockMessage, type KeyReadiness } from "@/lib/keys/readiness";

export const KEY_GATE_NOTICE_ID = "key-gate-notice";


const EXA_BANNER = "Metis will interview you but skip research: Exa isn't set up. Add a key in Settings to include it.";

interface KeyGateNoticeProps {
  gate: KeyReadiness;
  /** Show the Exa banner when only research is missing (where a new run can start). */
  includeExa: boolean;
}

/**
 * The line above the composer about saved keys: why a run cannot start (LLM key), else a banner
 * that research will be skipped (no Exa key). Nothing when both are fine.
 */
export function KeyGateNotice({ gate, includeExa }: KeyGateNoticeProps) {
  const blocked = gate.llmBlock !== null;
  if (!blocked && !(includeExa && gate.exaMissing)) return null;
  const Icon = blocked ? TriangleAlert : Info;
  return (
    <div
      id={KEY_GATE_NOTICE_ID}
      role="status"
      className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 border px-2.5 py-1.5"
    >
      <Icon size={14} aria-hidden="true" className="shrink-0 text-warning" />
      <span className="text-control">{blocked ? llmBlockMessage(gate.llmBlock) : EXA_BANNER}</span>
      <Link href={KEYS_SETTINGS_HREF} className="ml-auto text-control underline underline-offset-2 outline-none focus-visible:ring-2 focus-visible:ring-ring">
        Open API keys
      </Link>
    </div>
  );
}
