"use client";

import { ChevronDown, Plus, Building2, User } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useMe, useCreateWorkspace } from "@/lib/api";
import { useState } from "react";
import { useWorkspaceId } from "@/lib/api";

export function WorkspaceSwitcher() {
  const { data: me, isLoading } = useMe();
  const createWorkspace = useCreateWorkspace();
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const storedWorkspaceId = useWorkspaceId();

  // Determine current workspace
  const currentWorkspace = me?.current_workspace;
  const workspaces = me?.workspaces || [];

  const handleCreateWorkspace = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWorkspaceName.trim()) return;
    createWorkspace.mutate(newWorkspaceName.trim(), {
      onSuccess: () => setNewWorkspaceName(""),
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-2 py-2">
        <div className="h-5 w-20 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            className="w-full justify-between h-9 px-2 text-xs"
            aria-label="Switch workspace"
          >
            <div className="flex items-center gap-2 overflow-hidden">
              {currentWorkspace?.workspace.is_personal ? (
                <User className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
              ) : (
                <Building2 className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
              )}
              <span className="truncate font-medium">
                {currentWorkspace?.workspace.name || "Select workspace"}
              </span>
            </div>
            <ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="font-normal">
            Your Workspaces
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {workspaces.map((membership) => (
            <DropdownMenuItem
              key={membership.workspace.id}
              className={
                membership.workspace.id === storedWorkspaceId
                  ? "bg-accent text-accent-foreground"
                  : ""
              }
              onClick={() => {
                localStorage.setItem(
                  "metis_workspace_id",
                  membership.workspace.id
                );
                window.location.reload();
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {membership.workspace.is_personal ? (
                    <User className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <Building2 className="h-4 w-4 text-muted-foreground" />
                  )}
                  <span className="font-medium">
                    {membership.workspace.name}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground capitalize">
                  {membership.role}
                </span>
              </div>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <form onSubmit={handleCreateWorkspace} className="p-2">
            <div className="flex gap-2">
              <input
                type="text"
                value={newWorkspaceName}
                onChange={(e) => setNewWorkspaceName(e.target.value)}
                placeholder="New workspace name"
                className="flex-1 h-8 px-2 text-sm rounded-md border bg-background"
                maxLength={50}
              />
              <Button type="submit" size="icon" disabled={createWorkspace.isPending}>
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          </form>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}