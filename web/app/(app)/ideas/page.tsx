"use client";

import { useMe } from "@/lib/api";
import { Plus, Search, Filter, LayoutDashboard } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";

export default function IdeasPage() {
  const { data: _me, isLoading } = useMe();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 animate-pulse bg-muted rounded" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="h-40" />
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Ideas</h1>
          <p className="text-muted-foreground">
            Manage and track your ideas from concept to plan
          </p>
        </div>
        <Button className="gap-2">
          <Plus className="h-4 w-4" />
          New Idea
        </Button>
      </div>

      <div className="flex gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search ideas..."
            className="pl-10"
          />
        </div>
        <Button variant="outline" className="gap-2">
          <Filter className="h-4 w-4" />
          Filters
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Empty state */}
        <Card className="md:col-span-2 lg:col-span-3">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <LayoutDashboard className="h-12 w-12 text-muted-foreground/50" />
            <h3 className="mt-4 text-lg font-medium">No ideas yet</h3>
            <p className="mt-2 text-muted-foreground">
              Click &ldquo;New Idea&rdquo; to start planning your next project
            </p>
            <Button className="mt-4 gap-2" onClick={() => {}}>
              <Plus className="h-4 w-4" />
              Create your first idea
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}