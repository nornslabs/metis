"use client";

import { useMe } from "@/lib/api";
import { ProviderKeysTab } from "@/components/settings/ProviderKeysTab";
import { WorkspaceSettingsTab } from "@/components/settings/WorkspaceSettingsTab";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Building2, User, Key, Settings } from "lucide-react";

export default function SettingsPage() {
  const { data: me, isLoading } = useMe();

  const currentWorkspace = me?.current_workspace;
  const _isOwner = currentWorkspace?.role === "owner";

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-64 bg-muted rounded" />
        <div className="h-80 bg-muted rounded-lg" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-9">
      <div>
        <p className="mb-2 text-callout font-medium text-foreground-muted">Preferences</p>
        <h1 className="text-large-title">Settings</h1>
        <p className="mt-3 text-body text-foreground-muted">
          Manage the services and limits for this workspace.
        </p>
      </div>

      {/* Workspace Info */}
      <Card className="overflow-hidden">
        <CardHeader className="flex items-center gap-4 !p-5 sm:!p-6">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground-muted">
            {currentWorkspace?.workspace.is_personal ? (
              <User className="h-5 w-5" />
            ) : (
              <Building2 className="h-5 w-5" />
            )}
          </div>
          <div className="min-w-0">
            <p className="text-caption-1 text-foreground-muted">Current workspace</p>
            <CardTitle className="mt-0.5 truncate text-body-strong">{currentWorkspace?.workspace.name}</CardTitle>
          </div>
          <span className="ml-auto rounded-full bg-muted px-3 py-1 text-caption-1 font-medium capitalize text-foreground-muted">
              {currentWorkspace?.role}
          </span>
        </CardHeader>
      </Card>

      <Tabs defaultValue="keys" className="w-full">
        <TabsList className="grid w-full max-w-md grid-cols-2" aria-label="Settings tabs">
          <TabsTrigger value="keys">
            <Key className="mr-2 h-4 w-4" />
            <span>Provider Keys</span>
          </TabsTrigger>
          <TabsTrigger value="workspace">
            <Settings className="mr-2 h-4 w-4" />
            <span>Workspace</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="keys" className="pt-3 animate-fade-in">
          <Card>
            <CardHeader className="!pb-3">
              <CardTitle className="flex items-center gap-2">
                <Key className="h-5 w-5" />
                <span>BYO Provider Keys</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ProviderKeysTab />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="workspace" className="pt-3 animate-fade-in">
          <Card>
            <CardHeader className="!pb-3">
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                <span>Workspace Settings</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <WorkspaceSettingsTab />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
