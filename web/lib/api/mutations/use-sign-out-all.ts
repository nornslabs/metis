"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { apiClient } from "@/lib/api/client";
import { errorMessage, isApiError } from "@/lib/api/errors";
import { SIGN_IN_PATH } from "@/lib/auth/redirect";
import { toast } from "sonner";

/** Ends every session of the user (`POST /v1/auth/logout-all`), clears cached data, goes to sign-in. */
export function useSignOutAll() {
  const router = useRouter();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await apiClient.POST("/v1/auth/logout-all");
    },
    onError: (error) => {
      toast.error(isApiError(error) ? errorMessage(error) : "Couldn't sign out. Try again.");
    },
    onSuccess: () => {
      queryClient.clear();
      router.replace(SIGN_IN_PATH);
    },
  });
}
