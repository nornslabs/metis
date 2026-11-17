"use client";

import { Button } from "@/components/ui/button";
import { useSignOut } from "@/lib/auth/sign-out";

export function SignOutButton() {
  const signOut = useSignOut();
  return (
    <Button
      variant="outline"
      size="sm"
      disabled={signOut.isPending}
      onClick={() => signOut.mutate()}
    >
      Sign out
    </Button>
  );
}
