"use client";

import { useState } from "react";
import { Eye, EyeOff, CheckCircle, AlertCircle, Loader2, Trash2, Key } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSettings, useSetProviderKey, useDeleteProviderKey, useTestProviderKey } from "@/lib/api";
import { cn } from "@/lib/utils";

const KIND_LABELS: Record<"llm" | "exa", string> = {
  llm: "LLM (OpenAI-compatible)",
  exa: "Exa Research",
};

const KIND_DESCRIPTIONS: Record<"llm" | "exa", string> = {
  llm: "API key for OpenAI-compatible LLM provider (OpenAI, Anthropic, local, etc.)",
  exa: "API key for Exa AI research",
};

export function ProviderKeysTab() {
  const { data: settings, isLoading, error, refetch } = useSettings();
  const setKey = useSetProviderKey();
  const deleteKey = useDeleteProviderKey();
  const testKey = useTestProviderKey();

  const [showKey, setShowKey] = useState<Record<string, boolean>>({});
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; error?: string }>>({});
  const [testingKind, setTestingKind] = useState<"llm" | "exa" | null>(null);

  const providerKeys = settings?.provider_keys || {};

  const handleTest = async (kind: "llm" | "exa") => {
    setTestingKind(kind);
    try {
      const result = await testKey.mutateAsync(kind);
      setTestResults((prev) => ({ ...prev, [kind]: result }));
    } finally {
      setTestingKind(null);
    }
  };

  const handleDelete = async (kind: "llm" | "exa") => {
    if (!confirm(`Delete ${KIND_LABELS[kind]} key? This cannot be undone.`)) return;
    await deleteKey.mutateAsync(kind);
    refetch();
  };

  const handleAddKey = async (kind: "llm" | "exa", key: string) => {
    await setKey.mutateAsync({ kind, key });
    refetch();
  };

  const renderKeyRow = (kind: "llm" | "exa") => {
    const keyData = providerKeys[kind];
    const hasKey = !!keyData;
    const isOwner = true; // TODO: determine from workspace role

    if (!hasKey) {
      return (
        <AddKeyDialog
          key={kind}
          kind={kind}
          label={KIND_LABELS[kind]}
          description={KIND_DESCRIPTIONS[kind]}
          onAddKey={handleAddKey}
        />
      );
    }

    const maskedKey = keyData.masked_key;
    const testResult = testResults[kind];
    const isTesting = testingKind === kind;

    return (
      <div key={kind} className="flex items-center justify-between p-4 rounded-lg border border-border bg-card">
        <div className="flex items-center gap-4">
          <Key className="h-5 w-5 text-foreground-muted" />
          <div>
            <p className="text-body-strong">{KIND_LABELS[kind]}</p>
            <p className="text-caption-1 text-foreground-muted">{KIND_DESCRIPTIONS[kind]}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2">
              <code className="flex items-center gap-2 px-3 py-1.5 text-caption-1 font-mono bg-muted rounded-md">
                {maskedKey}
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="h-7 w-7 p-0"
                  onClick={() => setShowKey((prev) => ({ ...prev, [kind]: !prev[kind] }))}
                  aria-label={showKey[kind] ? "Hide key" : "Show key"}
                >
                  {showKey[kind] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </code>
              {testResult && (
                <span
                  className={cn(
                    "flex items-center gap-1.5 text-caption-1",
                    testResult.ok ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                  )}
                >
                  {testResult.ok ? (
                    <>
                      <CheckCircle className="h-4 w-4" /> Test passed
                    </>
                  ) : (
                    <>
                      <AlertCircle className="h-4 w-4" /> {testResult.error || "Failed"}
                    </>
                  )}
                </span>
              )}
            </div>
          </div>
          {isOwner && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleTest(kind)}
                disabled={testKey.isPending}
                aria-label={`Test ${KIND_LABELS[kind]} key`}
              >
                {isTesting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <span>Test</span>
                )}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => handleDelete(kind)}
                disabled={deleteKey.isPending}
                aria-label={`Delete ${KIND_LABELS[kind]} key`}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </div>
    );
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
    <div className="space-y-4">
      <Tabs defaultValue="llm" className="w-full">
        <TabsList className="grid w-full grid-cols-2" aria-label="Provider key types">
          <TabsTrigger value="llm">LLM Key</TabsTrigger>
          <TabsTrigger value="exa">Exa Key</TabsTrigger>
        </TabsList>
        <TabsContent value="llm" className="pt-4 animate-fade-in">
          {renderKeyRow("llm")}
        </TabsContent>
        <TabsContent value="exa" className="pt-4 animate-fade-in">
          {renderKeyRow("exa")}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function AddKeyDialog({
  kind,
  label,
  description,
  onAddKey,
}: {
  kind: "llm" | "exa";
  label: string;
  description: string;
  onAddKey: (kind: "llm" | "exa", key: string) => Promise<void>;
}) {
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!key.trim()) return;
    setError("");
    try {
      await onAddKey(kind, key.trim());
      setKey("");
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save key");
    }
  };

  return (
    <>
      <div className="flex items-center justify-between p-4 rounded-lg border border-border bg-card">
        <div>
          <p className="text-body-strong">{label}</p>
          <p className="text-caption-1 text-foreground-muted">{description}</p>
        </div>
        <Button onClick={() => setOpen(true)}>Add Key</Button>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Add {label} Key</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit}>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor={kind}>API Key</Label>
                <div className="relative">
                  <Input
                    id={kind}
                    type={showKey ? "text" : "password"}
                    value={key}
                    onChange={(e) => setKey(e.target.value)}
                    placeholder="sk-... or your API key"
                    autoComplete="off"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="absolute right-3 top-1/2 -translate-y-1/2 h-9 w-9"
                    onClick={() => setShowKey(!showKey)}
                    aria-label={showKey ? "Hide key" : "Show key"}
                  >
                    {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
              {error && <p className="text-caption-1 text-red-600 dark:text-red-400">{error}</p>}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!key.trim()}>
                Test & Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}