"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useQueryClient } from "@tanstack/react-query";
import { useCurrentWorkspace } from "@/lib/api/queries/use-current-workspace";
import { queryKeys } from "@/lib/api/queries/keys";
import { useWorkspaceId } from "@/lib/api/use-workspace-id";
import {
  connectErrorMessage,
  connectRedirectPath,
  readConnectReturn,
  withoutConnectReturn,
} from "@/lib/integrations/connect-return";

import { LinearCard } from "./linear-card";
import { SettingsGroup } from "./settings-field";

const NOTION_HINT = "Notion export is not available yet";

/** Reads the OAuth return once: refreshes the status, says what happened, and clears the params. */
function useConnectReturn() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  const handled = useRef<string | null>(null);
  const key = search.toString();
  useEffect(() => {
    const params = new URLSearchParams(key);
    const result = readConnectReturn(params);
    if (result === null || handled.current === key) return;
    handled.current = key;
    if (result.kind === "connected") {
      toast.success("Linear connected");
      void queryClient.invalidateQueries({ queryKey: queryKeys.integrations(workspaceId) });
    } else {
      toast.error("Could not connect Linear", { description: connectErrorMessage(result.code) });
    }
    router.replace(withoutConnectReturn(pathname, params));
  }, [key, pathname, router, queryClient, workspaceId]);
}

/** The Integrations tab: Linear (connect, status, tools) and Notion (not available yet). */
export function IntegrationsPanel() {
  const pathname = usePathname();
  const search = useSearchParams();
  const { data: current } = useCurrentWorkspace();
  useConnectReturn();

  return (
    <SettingsGroup title="Planning tools" hint="Export plans to Linear. The team is chosen when you export.">
      <LinearCard
        canWrite={current?.role === "owner"}
        redirectPath={connectRedirectPath(pathname, new URLSearchParams(search))}
      />
      <div className="flex items-center gap-2.5 border p-2.5 text-control">
        <span aria-hidden="true" className="grid size-7 shrink-0 place-items-center border font-semibold">
          N
        </span>
        <div className="min-w-0 flex-1">
          <b className="font-medium">Notion</b>
          <p className="text-meta text-muted-foreground">{NOTION_HINT}.</p>
        </div>
        <Button type="button" size="sm" disabled title={NOTION_HINT}>
          Connect
        </Button>
      </div>
    </SettingsGroup>
  );
}
