"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { signInHref } from "@/lib/auth/redirect";

/** Sends a signed-out visitor to `/sign-in`, remembering the page they asked for. */
export function RedirectToSignIn() {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const target = search ? `${pathname}?${search}` : pathname;

  useEffect(() => {
    window.location.replace(signInHref(target));
  }, [target]);

  return null;
}
