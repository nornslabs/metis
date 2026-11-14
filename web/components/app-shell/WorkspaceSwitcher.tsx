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
    <div className="space-y-3">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            className="w-full justify-between h-11 px-3 text-body"
            aria-label="Switch workspace"
          >
            <div className="flex items-center gap-2 overflow-hidden">
              {currentWorkspace?.workspace.is_personal ? (
                <User className="h-4 w-4 flex-shrink-0 text-foreground-muted" />
              ) : (
                <Building2 className="h-4 w-4 flex-shrink-0 text-foreground-muted" />
              )}
              <span className="truncate font-medium">
                {currentWorkspace?.workspace.name || "Select workspace"}
              </span>
            </div>
            <ChevronDown className="h-4 w-4 flex-shrink-0 text-foreground-muted" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          side="top"
          align="start"
          sideOffset={8}
          className="max-h-[min(26rem,calc(100dvh-2rem))] w-64 overflow-y-auto"
        >
          <DropdownMenuLabel className="font-medium">
            Your Workspaces
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {workspaces.map((membership) => (
            <DropdownMenuItem
              key={membership.workspace.id}
              className={
                membership.workspace.id === storedWorkspaceId
                  ? "bg-accent-bg text-accent"
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
                    <User className="h-4 w-4 text-foreground-muted" />
                  ) : (
                    <Building2 className="h-4 w-4 text-foreground-muted" />
                  )}
                  <span className="font-medium truncate">
                    {membership.workspace.name}
                  </span>
                </div>
                <span className="text-caption-1 text-foreground-muted capitalize">
                  {membership.role}
                </span>
              </div>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <form onSubmit={handleCreateWorkspace} className="p-3 space-y-2">
            <div className="flex gap-2">
              <input
                type="text"
                value={newWorkspaceName}
                onChange={(e) => setNewWorkspaceName(e.target.value)}
                placeholder="New workspace name"
                className="flex-1 h-10 px-3 text-body rounded-md border border-border bg-background placeholder:text-foreground-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
