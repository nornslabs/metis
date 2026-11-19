import { Info } from "lucide-react";
import Link from "next/link";

import type { RunNotice } from "@/lib/events/reducer";
import { KEYS_SETTINGS_HREF } from "@/lib/keys/readiness";

const ADD_EXA_CODE = "research.skipped_no_exa";

/** The server's notes about the run (e.g. research skipped), as quiet rows. Plain text only. */
export function RunNotices({ notices }: { notices: readonly RunNotice[] }) {
  if (notices.length === 0) return null;
  return (
    <ul aria-label="Notices" className="flex flex-col gap-1">
      {notices.map((notice) => (
        <li key={notice.code} role="status" className="flex flex-wrap items-center gap-x-2 gap-y-1 border px-2.5 py-1.5">
          <Info size={14} aria-hidden="true" className="shrink-0 text-muted-foreground" />
          <span className="text-body">{notice.text}</span>
          {notice.code === ADD_EXA_CODE ? (
            <Link href={KEYS_SETTINGS_HREF} className="ml-auto text-control underline underline-offset-2 outline-none focus-visible:ring-2 focus-visible:ring-ring">
              Add an Exa key for a new run
            </Link>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
