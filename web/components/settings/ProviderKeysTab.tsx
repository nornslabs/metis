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
      <div key={kind} className="flex items-center justify-between p-4 border rounded-lg bg-card">
        <div className="flex items-center gap-4">
          <Key className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="font-medium">{KIND_LABELS[kind]}</p>
            <p className="text-sm text-muted-foreground">{KIND_DESCRIPTIONS[kind]}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2">
            <code className="flex items-center gap-1 px-2 py-1 text-sm font-mono bg-muted rounded">
              {showKey[kind] ? maskedKey : maskedKey}
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 p-0"
                onClick={() => setShowKey((prev) => ({ ...prev, [kind]: !prev[kind] }))}
              >
                {showKey[kind] ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              </Button>
            </code>
            {testResult && (
              <span
                className={cn(
                  "flex items-center gap-1 text-xs",
                  testResult.ok ? "text-green-600" : "text-red-600"
                )}
              >
                {testResult.ok ? (
                  <>
                    <CheckCircle className="h-3.5 w-3.5" /> Test passed
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-3.5 w-3.5" /> {testResult.error || "Failed"}
                  </>
                )}
              </span>
            )}
          </div>
          {isOwner && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleTest(kind)}
                disabled={testKey.isPending}
              >
                {isTesting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Test"
                )}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => handleDelete(kind)}
                disabled={deleteKey.isPending}
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
      <div className="space-y-4">
        {[1, 2].map((i) => (
          <div key={i} className="h-20 animate-pulse bg-muted rounded-lg" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-red-600">Failed to load settings: {error.message}</div>
    );
  }

  return (
    <div className="space-y-4">
      <Tabs defaultValue="llm" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="llm">LLM Key</TabsTrigger>
          <TabsTrigger value="exa">Exa Key</TabsTrigger>
        </TabsList>
        <TabsContent value="llm" className="pt-4">
          {renderKeyRow("llm")}
        </TabsContent>
        <TabsContent value="exa" className="pt-4">
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
      <div className="flex items-center justify-between p-4 border rounded-lg bg-card">
        <div>
          <p className="font-medium">{label}</p>
          <p className="text-sm text-muted-foreground">{description}</p>
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
                    size="icon"
                    className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8"
                    onClick={() => setShowKey(!showKey)}
                  >
                    {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
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