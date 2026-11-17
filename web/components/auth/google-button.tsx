"use client";

import { useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M21.35 11.1H12v2.98h5.35c-.23 1.4-1.66 4.1-5.35 4.1-3.22 0-5.85-2.67-5.85-5.96S8.78 6.26 12 6.26c1.83 0 3.06.78 3.76 1.45l2.56-2.47C16.68 3.7 14.55 2.75 12 2.75 6.89 2.75 2.75 6.89 2.75 12S6.89 21.25 12 21.25c5.34 0 8.88-3.75 8.88-9.04 0-.6-.07-1.06-.15-1.51Z"
      />
    </svg>
  );
}

/** A plain link to the server's login route; the server redirects on to Google. */
export function GoogleButton({ redirectTo }: { redirectTo: string }) {
  const [pending, setPending] = useState(false);
  const href = `/v1/auth/google/login?redirect_to=${encodeURIComponent(redirectTo)}`;
  return (
    <a
      href={href}
      aria-busy={pending}
      onClick={() => setPending(true)}
      className={cn(buttonVariants({ size: "lg" }), "h-8 w-full text-control")}
    >
      {pending ? (
        <>
          <span
            aria-hidden="true"
            className="size-3.5 animate-spin rounded-full border-2 border-current border-r-transparent motion-reduce:animate-none"
          />
          <span>Redirecting to Google…</span>
        </>
      ) : (
        <>
          <GoogleMark />
          <span>Continue with Google</span>
        </>
      )}
    </a>
  );
}
