"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { SIGN_IN_PATH } from "./redirect";

async function postLogout(): Promise<void> {
  const response = await fetch("/v1/auth/logout", {
    method: "POST",
    credentials: "include",
    headers: { "X-Metis-Client": "web" },
  });
  if (!response.ok) {
    throw new Error(`Sign out failed with status ${response.status}`);
  }
}

/** Ends the session on the server, clears cached data and goes to the sign-in page. */
export function useSignOut() {
  const router = useRouter();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: postLogout,
    onError: () => {
      toast.error("Couldn't sign out. Try again.");
    },
    onSuccess: () => {
      queryClient.clear();
      router.replace(SIGN_IN_PATH);
    },
  });
}
