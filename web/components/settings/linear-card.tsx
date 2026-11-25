"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/settings/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { describeError } from "@/lib/api/errors";
import { useConnectLinear, useDisconnectLinear } from "@/lib/api/mutations/use-integration-actions";
import { useLinearStatus, useLinearTools, type IntegrationStatus } from "@/lib/api/queries/use-integrations";
import { cn } from "@/lib/cn";

const OWNER_ONLY_HINT = "Only workspace owners can change this.";

const STATUS_TEXT: Readonly<Record<IntegrationStatus, string>> = {
  not_connected: "Not connected",
  connected: "Connected",
  expired: "Expired",
};

const STATUS_TONE: Readonly<Record<IntegrationStatus, string>> = {
  not_connected: "text-muted-foreground",
  connected: "text-success",
  expired: "text-warning",
};

function connectedOn(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleDateString(undefined, { dateStyle: "medium" });
}

function ToolsList({ open }: { open: boolean }) {
  const tools = useLinearTools(open);
  if (!open) return null;
  if (tools.unavailable) {
    return <p className="text-meta text-muted-foreground">Reconnect to load tools.</p>;
  }
  if (tools.isPending) return <Skeleton aria-label="Loading tools" className="h-16" />;
  if (tools.isError) {
    return (
      <p role="alert" className="text-meta text-destructive">
        {describeError(tools.error)}
      </p>
    );
  }
  if (tools.data.length === 0) return <p className="text-meta text-muted-foreground">Linear offers no tools.</p>;
  return (
    <ul className="grid gap-1.5 border-t pt-2">
      {tools.data.map((tool) => (
        <li key={tool.name} className="grid gap-0.5">
          <span className="font-mono text-meta">{tool.name}</span>
          {tool.description ? <span className="text-meta text-muted-foreground">{tool.description}</span> : null}
        </li>
      ))}
    </ul>
  );
}

interface LinearCardProps {
  /** Only owners connect, reconnect or disconnect. */
  canWrite: boolean;
  /** The path the server returns the browser to after the OAuth flow. */
  redirectPath: string;
}

/** The Linear tile: status, Connect / Reconnect / Disconnect, and the tools Linear offers. */
export function LinearCard({ canWrite, redirectPath }: LinearCardProps) {
  const { status, connection, isPending } = useLinearStatus();
  const connect = useConnectLinear();
  const disconnect = useDisconnectLinear();
  const [toolsOpen, setToolsOpen] = useState(false);

  const startConnect = () =>
    connect.mutate(redirectPath, {
      onSuccess: (authorizeUrl) => window.location.assign(authorizeUrl),
      onError: (error) => toast.error("Could not start the connection", { description: describeError(error) }),
    });
  const startDisconnect = () =>
    disconnect.mutate(undefined, {
      onSuccess: () => toast.success("Linear disconnected"),
      onError: (error) => toast.error("Could not disconnect", { description: describeError(error) }),
    });

  if (isPending) return <Skeleton aria-label="Loading Linear" className="h-20" />;
  const since = connectedOn(connection?.connected_at);
  const hint = canWrite ? undefined : OWNER_ONLY_HINT;
  const needsConnect = status !== "connected";
  return (
    <div className="grid gap-2.5 border p-2.5 text-control">
      <div className="flex items-center gap-2.5">
        <span aria-hidden="true" className="grid size-7 shrink-0 place-items-center border bg-foreground font-semibold text-background">
          L
        </span>
        <div className="min-w-0 flex-1">
          <b className="font-medium">Linear</b>
          <p className="text-meta text-muted-foreground">Export phases and issues with dependencies.</p>
        </div>
        <span role="status" className={cn("text-meta", STATUS_TONE[status])}>
          {STATUS_TEXT[status]}
        </span>
      </div>
      {status === "connected" && since ? <p className="text-meta text-muted-foreground">{`Connected ${since}`}</p> : null}
      {status === "expired" ? (
        <p role="alert" className="text-meta text-warning">
          The connection expired. Reconnect to export again.
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-1.5">
        {needsConnect ? (
          <Button
            type="button"
            size="sm"
            disabled={!canWrite || connect.isPending}
            title={hint}
            onClick={startConnect}
          >
            {status === "expired" ? "Reconnect" : "Connect"}
          </Button>
        ) : (
          <ConfirmDialog
            trigger={
              <Button type="button" variant="outline" size="sm" disabled={!canWrite || disconnect.isPending} title={hint} />
            }
            title="Disconnect Linear?"
            description="Metis can no longer export to Linear until you connect it again. Items already in Linear stay."
            confirmLabel="Disconnect"
            onConfirm={startDisconnect}
          />
        )}
        {!canWrite ? <span className="text-meta text-muted-foreground">{OWNER_ONLY_HINT}</span> : null}
      </div>
      {status !== "not_connected" ? (
        <div className="grid gap-1.5">
          <button
            type="button"
            aria-expanded={toolsOpen}
            onClick={() => setToolsOpen((open) => !open)}
            className="flex items-center gap-1 text-left text-meta text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:text-foreground"
          >
            <ChevronRight size={12} aria-hidden="true" className={cn("transition-transform", toolsOpen && "rotate-90")} />
            Tools
          </button>
          <ToolsList open={toolsOpen} />
        </div>
      ) : null}
    </div>
  );
}
