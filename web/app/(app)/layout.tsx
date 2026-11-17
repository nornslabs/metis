import { Suspense, type ReactNode } from "react";

import { RedirectToSignIn } from "@/components/auth/redirect-to-sign-in";
import { getMe } from "@/lib/auth/get-me";

// Reads the session behind its own Suspense boundary, next to `children` rather than around them,
// so every app page still renders (and validates) on its own. The API enforces auth on all data.
async function AuthGate() {
  const me = await getMe();
  return me ? null : <RedirectToSignIn />;
}

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Suspense fallback={null}>
        <AuthGate />
      </Suspense>
      {children}
    </>
  );
}
