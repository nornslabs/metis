"use client";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { onWorkspaceRejected } from "@/lib/api/client";
import { shouldRetry } from "@/lib/api/retry";
import { createSessionExpiryHandler } from "@/lib/api/session-expiry";
import { signInHref } from "@/lib/auth/redirect";

export function QueryProvider({ children }: { children: ReactNode }) {
  const router = useRouter();

  const [{ client, expiry }] = useState(() => {
    const expiry = createSessionExpiryHandler();
    const client = new QueryClient({
      queryCache: new QueryCache({ onError: expiry.handle, onSuccess: expiry.rearm }),
      mutationCache: new MutationCache({ onError: expiry.handle }),
      defaultOptions: { queries: { retry: shouldRetry } },
    });
    return { client, expiry };
  });

  useEffect(() => {
    expiry.setOnExpired(() => {
      client.clear();
      toast("Signed out");
      const { pathname, search } = window.location;
      router.replace(signInHref(`${pathname}${search}`));
    });
  }, [client, expiry, router]);

  // A refused workspace was dropped from the cookie: refetch so the server falls back to the
  // personal workspace.
  useEffect(() => onWorkspaceRejected(() => void client.invalidateQueries()), [client]);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
