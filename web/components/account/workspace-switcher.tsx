"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ChevronsUpDown, Plus } from "lucide-react";
import { useRouter } from "next/navigation";

import {
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
} from "@/components/ui/dropdown-menu";
import { useCurrentWorkspace } from "@/lib/api/queries/use-current-workspace";
import { useWorkspaces } from "@/lib/api/queries/use-workspaces";
import { setWorkspaceId } from "@/lib/api/workspace";

/** Switches the workspace that later API calls (`X-Workspace-Id`) belong to; the choice is a cookie. */
export function useSwitchWorkspace(): (workspaceId: string) => void {
  const queryClient = useQueryClient();
  const router = useRouter();
  return (workspaceId) => {
    setWorkspaceId(workspaceId);
    // Everything but the signed-in user belongs to the previous workspace.
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "me" });
    router.refresh();
  };
}

export function WorkspaceSwitcher({ onCreate }: { onCreate: () => void }) {
  const { data: current } = useCurrentWorkspace();
  const { data: memberships } = useWorkspaces();
  const switchWorkspace = useSwitchWorkspace();
  const currentId = current?.workspace.id ?? "";

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger className="h-7 text-control">
        <ChevronsUpDown size={14} />
        <span className="truncate">{current?.workspace.name ?? "Workspace"}</span>
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-59">
        <DropdownMenuRadioGroup
          value={currentId}
          onValueChange={(id) => {
            if (id !== currentId) switchWorkspace(id);
          }}
        >
          {memberships?.items.map(({ workspace }) => (
            <DropdownMenuRadioItem key={workspace.id} value={workspace.id} className="h-7 text-control">
              <span className="truncate">{workspace.name}</span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem className="h-7 text-control" onClick={onCreate}>
          <Plus size={14} />
          New workspace
        </DropdownMenuItem>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}
