"use client";

import { Check, KeyRound, LogOut, Plug, Settings } from "lucide-react";
import { useState } from "react";

import { ThemeSegment } from "@/components/account/theme-segment";
import { UserAvatar } from "@/components/account/user-avatar";
import { WorkspaceSwitcher } from "@/components/account/workspace-switcher";
import { NewWorkspaceDialog } from "@/components/account/new-workspace-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useMe } from "@/lib/api/queries/use-me";
import { useSettings } from "@/lib/api/queries/use-settings";
import { useSignOut } from "@/lib/auth/sign-out";
import { useOpenSettings } from "@/lib/settings/use-open-settings";

export const ACCOUNT_TRIGGER_ID = "account-menu-trigger";

/** Count of provider keys that are saved. */
function savedKeyCount(keys: { llm?: unknown; exa?: unknown } | undefined): number {
  if (!keys) return 0;
  return [keys.llm, keys.exa].filter(Boolean).length;
}

export function AccountMenu() {
  const { data: me } = useMe();
  const { data: settings } = useSettings();
  const openSettings = useOpenSettings();
  const signOut = useSignOut();
  const [creatingWorkspace, setCreatingWorkspace] = useState(false);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          id={ACCOUNT_TRIGGER_ID}
          aria-label="Account"
          className="ml-1.5 border border-transparent outline-none hover:border-ring focus-visible:ring-2 focus-visible:ring-ring aria-expanded:border-ring"
        >
          <UserAvatar name={me?.name ?? null} email={me?.email ?? "?"} image={me?.image ?? null} />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={6} className="w-59 p-0.5">
          <div className="flex items-center gap-2 px-2 pt-1.5 pb-2">
            <UserAvatar
              name={me?.name ?? null}
              email={me?.email ?? "?"}
              image={me?.image ?? null}
              className="size-7"
            />
            <div className="min-w-0">
              <div className="truncate text-body font-medium">{me?.name ?? me?.email ?? "…"}</div>
              <div className="truncate text-meta text-muted-foreground">
                {me?.email ?? "Signed in with Google"}
              </div>
            </div>
          </div>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <WorkspaceSwitcher onCreate={() => setCreatingWorkspace(true)} />
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuItem className="h-7 text-control" onClick={() => openSettings("account")}>
              <Settings size={14} />
              Settings
              <DropdownMenuShortcut>⌘,</DropdownMenuShortcut>
            </DropdownMenuItem>
            <DropdownMenuItem className="h-7 text-control" onClick={() => openSettings("keys")}>
              <KeyRound size={14} />
              API keys
              <span className="ml-auto flex items-center gap-1 text-meta text-muted-foreground">
                {savedKeyCount(settings?.keys) > 0 ? <Check size={12} /> : null}
                {savedKeyCount(settings?.keys)}/2
              </span>
            </DropdownMenuItem>
            <DropdownMenuItem
              className="h-7 text-control"
              onClick={() => openSettings("integrations")}
            >
              <Plug size={14} />
              Integrations
            </DropdownMenuItem>
          </DropdownMenuGroup>
          <div className="px-2 pt-1.5 pb-0.5 text-micro font-medium tracking-label text-muted-foreground uppercase">
            Theme
          </div>
          <ThemeSegment className="mx-2 mt-0.5 mb-1.5" />
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            className="h-7 text-control"
            onClick={() => signOut.mutate()}
          >
            <LogOut size={14} />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <NewWorkspaceDialog open={creatingWorkspace} onOpenChange={setCreatingWorkspace} />
    </>
  );
}
