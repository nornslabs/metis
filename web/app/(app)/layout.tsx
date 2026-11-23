import { Suspense, type ReactNode } from "react";

import { RedirectToSignIn } from "@/components/auth/redirect-to-sign-in";
import { AppFrame } from "@/components/frame/app-frame";
import { WorkspaceLayout } from "@/components/workspace/workspace-layout";
import { SettingsShortcut } from "@/components/settings/settings-shortcut";
import { SettingsSheet } from "@/components/settings/settings-sheet";
import { getMe } from "@/lib/auth/get-me";

// Reads the session behind its own Suspense boundary, next to `children` rather than around them,
// so every app page still renders (and validates) on its own. The API enforces auth on all data.
async function AuthGate() {
  const me = await getMe();
  return me ? null : <RedirectToSignIn />;
}

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AppFrame>
      <Suspense fallback={null}>
        <AuthGate />
      </Suspense>
      <WorkspaceLayout>{children}</WorkspaceLayout>
      {/* `useSearchParams` needs a boundary; the sheet and its shortcut hang off `?settings=`. */}
      <Suspense fallback={null}>
        <SettingsSheet />
        <SettingsShortcut />
      </Suspense>
    </AppFrame>
  );
}
