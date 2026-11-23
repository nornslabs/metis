import { BrandMark } from "@/components/brand/brand-mark";
import { Badge } from "@/components/ui/badge";

import { ThemeToggle } from "./theme-toggle";

export function AuthHeader() {
  return (
    <header className="relative z-10 h-(--header-h) shrink-0 border-b">
      <div className="mx-auto flex h-full w-(--frame) items-center justify-between px-4">
        <div className="flex items-center gap-2 font-semibold tracking-tight">
          <BrandMark />
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
