"use client";

import { useMe } from "@/lib/api";
import { useState } from "react";
import { Plus, Search, Filter, Lightbulb, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const lifecycleStages = ["interview", "research", "scoring", "spec", "planning"] as const;
type LifecycleStage = (typeof lifecycleStages)[number];

const lifecycleStageLabels: Record<LifecycleStage, string> = {
  interview: "Interview",
  research: "Research",
  scoring: "Scoring",
  spec: "Specification",
  planning: "Planning",
};

export default function IdeasPage() {
  const { isLoading } = useMe();
  const [newIdeaOpen, setNewIdeaOpen] = useState(false);
  const [ideaTitle, setIdeaTitle] = useState("");
  const [ideaDescription, setIdeaDescription] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [lifecycleStage, setLifecycleStage] = useState<"all" | LifecycleStage>("all");

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-48 bg-muted rounded" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="h-40" />
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-10">
      <div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-callout font-medium text-foreground-muted">Your workspace</p>
          <h1 className="text-large-title">Ideas</h1>
          <p className="mt-3 max-w-lg text-body text-foreground-muted">
            A clear place to shape early thoughts into something real.
          </p>
        </div>
        <Button className="h-11 gap-2 self-start px-5 sm:self-auto" onClick={() => setNewIdeaOpen(true)}>
          <Plus className="h-4 w-4" />
          <span>New idea</span>
        </Button>
      </div>

      <div className="flex flex-col gap-3 border-b pb-5 sm:flex-row sm:items-center">
        <div className="relative w-full sm:max-w-sm">
          <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground-muted" aria-hidden="true" />
          <Input
            aria-label="Search ideas"
            placeholder="Search ideas..."
            className="h-10 pl-10"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                className="h-10 gap-2 px-3"
                aria-label={lifecycleStage === "all" ? "Filter ideas by lifecycle stage" : `Filter ideas by lifecycle stage: ${lifecycleStageLabels[lifecycleStage]}`}
                aria-haspopup="menu"
              >
                <Filter className="h-4 w-4" />
                <span>Filters</span>
                {lifecycleStage !== "all" && <span className="ml-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-accent-bg px-1 text-caption-1 text-accent">1</span>}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-64">
              <DropdownMenuLabel>Lifecycle stage</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuRadioGroup value={lifecycleStage} onValueChange={(value) => setLifecycleStage(value as "all" | LifecycleStage)}>
                <DropdownMenuRadioItem value="all">All stages</DropdownMenuRadioItem>
                {lifecycleStages.map((stage) => (
                  <DropdownMenuRadioItem key={stage} value={stage}>
                    {lifecycleStageLabels[stage]}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
          {(lifecycleStage !== "all" || searchTerm) && (
            <Button
              variant="ghost"
              size="sm"
              className="h-10 px-2 text-foreground-muted"
              onClick={() => {
                setLifecycleStage("all");
                setSearchTerm("");
              }}
            >
              <X className="h-3.5 w-3.5" />
              Clear
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Empty state */}
        <Card className="min-h-[340px] md:col-span-2 lg:col-span-3">
          <CardContent className="flex min-h-[340px] flex-col items-center justify-center px-6 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-bg text-accent">
              <Lightbulb className="h-6 w-6" strokeWidth={1.7} />
            </div>
            <h2 className="mt-5 text-title-2">
              {searchTerm || lifecycleStage !== "all" ? "No matching ideas" : "Start with a thought"}
            </h2>
            <p className="mt-2 max-w-sm text-callout text-foreground-muted">
              {searchTerm || lifecycleStage !== "all"
                ? "No ideas match the current search and lifecycle stage. Try changing or clearing your filters."
                : "Capture an idea, question, or ambition. Metis will help you turn it into a thoughtful plan."}
            </p>
            <Button className="mt-6 h-10 gap-2 px-4" onClick={() => setNewIdeaOpen(true)}>
              <Plus className="h-4 w-4" />
              <span>Create an idea</span>
            </Button>
          </CardContent>
        </Card>
      </div>

      <Dialog open={newIdeaOpen} onOpenChange={setNewIdeaOpen}>
        <DialogContent className="w-[calc(100%-2rem)] max-w-lg rounded-2xl p-0">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setNewIdeaOpen(false);
            }}
          >
            <DialogHeader className="p-6 pb-4 text-left sm:p-7 sm:pb-4">
              <DialogTitle className="text-title-2">A new idea</DialogTitle>
              <DialogDescription className="mt-1 text-callout text-foreground-muted">
                Start with the thought you want to explore. You can add more detail as it takes shape.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 px-6 pb-6 sm:px-7">
              <div className="space-y-2">
                <Label htmlFor="idea-title">Idea</Label>
                <Input
                  id="idea-title"
                  autoFocus
                  autoComplete="off"
                  placeholder="Give your idea a name"
                  value={ideaTitle}
                  onChange={(event) => setIdeaTitle(event.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="idea-description">A little context <span className="font-normal text-foreground-muted">(optional)</span></Label>
                <textarea
                  id="idea-description"
                  className="min-h-28 w-full resize-y rounded-xl border border-input-border bg-input px-3.5 py-3 text-body text-foreground placeholder:text-foreground-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder="What sparked it? What would you like to find out?"
                  value={ideaDescription}
                  onChange={(event) => setIdeaDescription(event.target.value)}
                  rows={4}
                />
              </div>
            </div>
            <DialogFooter className="flex-row justify-end gap-2 border-t px-6 py-4 sm:px-7">
              <Button type="button" variant="ghost" onClick={() => setNewIdeaOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!ideaTitle.trim()}>
                Continue
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
