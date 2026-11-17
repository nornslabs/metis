import { Layers } from "lucide-react";

import { Badge } from "@/components/ui/badge";

import { ThemeToggle } from "./theme-toggle";

export function AuthHeader() {
  return (
    <header className="relative z-10 h-(--header-h) shrink-0 border-b">
      <div className="mx-auto flex h-full w-(--frame) items-center justify-between px-4">
        <div className="flex items-center gap-2 font-semibold tracking-tight">
          <span
            aria-hidden="true"
            className="grid size-5 place-items-center bg-primary text-primary-foreground"
          >
            <Layers size={12} strokeWidth={2} />
          </span>
          Metis
          <Badge variant="outline" className="h-badge px-1.5 text-meta font-medium text-muted-foreground">
            Beta
          </Badge>
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}
