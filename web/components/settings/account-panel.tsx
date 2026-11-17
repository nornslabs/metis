"use client";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { useSignOutAll } from "@/lib/api/mutations/use-sign-out-all";
import { useCurrentWorkspace } from "@/lib/api/queries/use-current-workspace";
import { useMe } from "@/lib/api/queries/use-me";

import { ConfirmDialog } from "./confirm-dialog";
import { Field, SettingsGroup } from "./settings-field";

const READ_ONLY_INPUT = "h-control bg-muted text-control text-muted-foreground";

/** Who and where: read-only profile and workspace, plus sign out on every device. */
export function AccountPanel() {
  const { data: me } = useMe();
  const { data: current } = useCurrentWorkspace();
  const signOutAll = useSignOutAll();

  if (!me || !current) return <Skeleton className="h-40" />;

  return (
    <div className="grid gap-4.5">
      <SettingsGroup title="Profile">
        <Field id="account-name" label="Name">
          <Input id="account-name" readOnly value={me.name ?? ""} className={READ_ONLY_INPUT} />
        </Field>
        <Field id="account-email" label="Email" hint="You sign in with Google.">
          <Input id="account-email" readOnly value={me.email} className={READ_ONLY_INPUT} />
        </Field>
      </SettingsGroup>
      <SettingsGroup title="Workspace">
        <Field id="account-workspace" label="Workspace name" hint={`Your role: ${current.role}.`}>
          <Input
            id="account-workspace"
            readOnly
            value={current.workspace.name}
            className={READ_ONLY_INPUT}
          />
        </Field>
      </SettingsGroup>
      <SettingsGroup title="Sessions">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-control font-medium">Sign out all devices</div>
            <div className="text-meta text-muted-foreground">Ends every session on every device.</div>
          </div>
          <ConfirmDialog
            trigger={
              <Button variant="outline" size="sm" disabled={signOutAll.isPending}>
                Sign out all
              </Button>
            }
            title="Sign out all devices?"
            description="Every session of your account ends, including this one."
            confirmLabel="Sign out all"
            onConfirm={() => signOutAll.mutate()}
          />
        </div>
      </SettingsGroup>
    </div>
  );
}
