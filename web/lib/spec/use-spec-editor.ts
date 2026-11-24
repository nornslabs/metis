"use client";

import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useMemo, useSyncExternalStore } from "react";

import { confirmSpecVersion, fetchSpecOverview, saveSpecVersion } from "@/lib/api/mutations/spec";
import { queryKeys } from "@/lib/api/queries/keys";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";
import { SpecEditor, type SpecEditorState } from "@/lib/spec/spec-editor";

/** Editors per query client, so none outlives the client (and the session) it was built for. */
const editorsByClient = new WeakMap<QueryClient, Map<string, SpecEditor>>();

function createEditor(queryClient: QueryClient, workspaceId: string | null, ideaId: string): SpecEditor {
  const key = queryKeys.spec(workspaceId, ideaId);
  return new SpecEditor({
    save: (baseNumber, contentMd) => saveSpecVersion(ideaId, baseNumber, contentMd),
    confirm: async (number) => {
      const result = await confirmSpecVersion(ideaId, number);
      // The idea moves to `spec_confirmed` and the run moves on: refetch what depends on them.
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs(workspaceId, ideaId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.idea(workspaceId, ideaId), exact: true });
      return result;
    },
    refresh: async () => {
      const overview = await fetchSpecOverview(ideaId);
      queryClient.setQueryData(key, overview);
      return overview;
    },
    publish: (overview) => queryClient.setQueryData(key, overview),
  });
}

/** The one editor of an idea's spec, shared by the pane, its footer and the chat prompt. */
export function useSpecEditor(ideaId: string): SpecEditor {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  return useMemo(() => {
    const editors = editorsByClient.get(queryClient) ?? new Map<string, SpecEditor>();
    editorsByClient.set(queryClient, editors);
    const id = `${workspaceId ?? ""}:${ideaId}`;
    const existing = editors.get(id);
    if (existing) return existing;
    const created = createEditor(queryClient, workspaceId, ideaId);
    editors.set(id, created);
    return created;
  }, [queryClient, workspaceId, ideaId]);
}

/** The editor's state, re-rendering on every change. */
export function useSpecEditorState(editor: SpecEditor): SpecEditorState {
  return useSyncExternalStore(editor.subscribe, editor.getState, editor.getState);
}
