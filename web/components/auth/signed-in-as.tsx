"use client";

import { useMe } from "@/lib/api/queries/use-me";

/** The signed-in user's email, read through the typed client with only the session cookie. */
export function SignedInAs() {
  const { data: me } = useMe();
  if (!me) return <div className="h-5 w-48 animate-pulse bg-muted motion-reduce:animate-none" />;
  return <p className="text-muted-foreground">Signed in as {me.email}.</p>;
}
