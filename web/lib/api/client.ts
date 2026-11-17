"use client";

import { createApiClient } from "./create-client";
import { clearWorkspaceId, getWorkspaceId } from "./workspace";

let workspaceRejectedListener: () => void = () => undefined;

/** Registers what happens after the workspace cookie is cleared (the query provider refetches). */
export function onWorkspaceRejected(listener: () => void): () => void {
  workspaceRejectedListener = listener;
  return () => {
    workspaceRejectedListener = () => undefined;
  };
}

/**
 * The browser API client: same origin (the `/v1` rewrite), session cookie included. Server
 * components use `getServerClient()` instead.
 */
export const apiClient = createApiClient({
  baseUrl: "",
  credentials: "include",
  getWorkspaceId,
  onWorkspaceRejected: () => {
    clearWorkspaceId();
    workspaceRejectedListener();
  },
});
