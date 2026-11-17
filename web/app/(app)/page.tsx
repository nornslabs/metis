import { Suspense } from "react";

import { SignOutButton } from "@/components/auth/sign-out-button";
import { getMe } from "@/lib/auth/get-me";

async function SignedInAs() {
  const me = await getMe();
  return me ? <p className="text-muted-foreground">Signed in as {me.email}.</p> : null;
}

// Placeholder until the app shell (SHIP-224): proves the guard and sign-out.
export default function HomePage() {
  return (
    <main className="flex flex-1 flex-col items-start justify-center gap-3 p-6">
      <h1 className="text-xl font-semibold tracking-tight">What are you building?</h1>
      <Suspense
        fallback={<div className="h-5 w-48 animate-pulse bg-muted motion-reduce:animate-none" />}
      >
        <SignedInAs />
      </Suspense>
      <SignOutButton />
    </main>
  );
}
