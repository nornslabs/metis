"use client";

import { useState } from "react";
import { Loader2, Save, AlertCircle, CheckCircle, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSettings, useUpdateSettings } from "@/lib/api";

export function WorkspaceSettingsTab() {
  const { data: settings, isLoading, error } = useSettings();
  const updateSettings = useUpdateSettings();

  const [runBudget, setRunBudget] = useState("");
  const [maxSteps, setMaxSteps] = useState("");
  const [version, setVersion] = useState(0);
  const [saved, setSaved] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const workspaceSettings = settings?.workspace_settings;
  const isOwner = true; // TODO: determine from workspace role

  // Initialize form values
  if (workspaceSettings && !runBudget) {
    setRunBudget(workspaceSettings.run_budget_usd.toFixed(2));
    setMaxSteps(workspaceSettings.max_steps.toString());
    setVersion(workspaceSettings.version);
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isOwner) return;

    setErrorMsg("");
    setSaved(false);

    try {
      await updateSettings.mutateAsync({
        run_budget_usd: parseFloat(runBudget),
        max_steps: parseInt(maxSteps, 10),
        version,
      });
      setSaved(true);
      setVersion((v) => v + 1);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to save settings");
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        {[1, 2].map((i) => (
          <div key={i} className="h-20 rounded-lg bg-muted" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-md bg-destructive-bg text-destructive text-callout">
        Failed to load settings: {error.message}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Workspace Settings
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <form onSubmit={handleSubmit} className="space-y-6 max-w-xl">
            <div className="space-y-2">
              <Label htmlFor="run_budget_usd">Run Budget (USD)</Label>
              <div className="relative">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-foreground-muted">$</span>
                <Input
                  id="run_budget_usd"
                  type="number"
                  step="0.01"
                  min="0.01"
                  max="100"
                  value={runBudget}
                  onChange={(e) => setRunBudget(e.target.value)}
                  className="pl-10 h-11"
                  disabled={!isOwner}
                />
              </div>
              <p className="text-caption-1 text-foreground-muted">
                Maximum cost per run. Range: $0.01 - $100.00
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="max_steps">Max Steps</Label>
              <Input
                id="max_steps"
                type="number"
                min="1"
                max="200"
                value={maxSteps}
                onChange={(e) => setMaxSteps(e.target.value)}
                className="h-11"
                disabled={!isOwner}
              />
              <p className="text-caption-1 text-foreground-muted">
                Maximum number of agent steps per run. Range: 1 - 200
              </p>
            </div>

            {!isOwner && (
              <p className="text-caption-1 text-foreground-muted flex items-center gap-1.5">
                <AlertCircle className="h-4 w-4" />
                Only workspace owners can modify these settings.
              </p>
            )}

            {isOwner && (
              <Button type="submit" disabled={updateSettings.isPending} className="w-full sm:w-auto">
                {updateSettings.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : saved ? (
                  <>
                    <CheckCircle className="mr-2 h-4 w-4" />
                    Saved
                  </>
                ) : (
                  <>
                    <Save className="mr-2 h-4 w-4" />
                    Save Settings
                  </>
                )}
              </Button>
            )}

            {errorMsg && (
              <p className="text-caption-1 text-red-600 dark:text-red-400 flex items-center gap-1.5">
                <AlertCircle className="h-4 w-4" />
                {errorMsg}
              </p>
            )}

            <p className="text-caption-2 text-foreground-muted">
              Current version: {version}
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}