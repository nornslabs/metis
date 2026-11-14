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
      <div className="space-y-4">
        <div className="h-8 w-64 animate-pulse bg-muted rounded" />
        <div className="h-80 animate-pulse bg-muted rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage your provider keys and workspace settings
        </p>
      </div>

      {/* Workspace Info */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-lg">
            {currentWorkspace?.workspace.is_personal ? (
              <User className="h-5 w-5" />
            ) : (
              <Building2 className="h-5 w-5" />
            )}
            <span>{currentWorkspace?.workspace.name}</span>
            <span className="px-2 py-0.5 text-xs rounded-full bg-muted">
              {currentWorkspace?.role}
            </span>
          </CardTitle>
        </CardHeader>
      </Card>

      <Tabs defaultValue="keys" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="keys">
            <Key className="mr-2 h-4 w-4" />
            Provider Keys
          </TabsTrigger>
          <TabsTrigger value="workspace">
            <Settings className="mr-2 h-4 w-4" />
            Workspace
          </TabsTrigger>
        </TabsList>

        <TabsContent value="keys" className="pt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Key className="h-5 w-5" />
                BYO Provider Keys
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ProviderKeysTab />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="workspace" className="pt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Workspace Settings
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