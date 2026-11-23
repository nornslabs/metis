import { SquarePen } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account/account-menu";
import { BrandMark } from "@/components/brand/brand-mark";
import { ThemeToggle } from "@/components/auth/theme-toggle";
import { HeaderCrumb } from "@/components/frame/header-crumb";
import { RecentIdeas } from "@/components/frame/recent-ideas";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function AppHeader() {
  return (
    <header data-frame="header" className="relative z-20 h-(--header-h) shrink-0 border-b">
      <div className="mx-auto flex h-full w-(--frame) items-center justify-between px-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex items-center gap-2 font-semibold tracking-tight">
            <BrandMark />
            Metis
            <Badge
              variant="outline"
              className="h-badge px-1.5 text-meta font-medium text-muted-foreground max-compact:hidden"
            >
              Beta
            </Badge>
          </div>
          {/* Route params are request data: read them behind a boundary so the header still prerenders. */}
          <Suspense fallback={null}>
            <HeaderCrumb />
          </Suspense>
        </div>
        <div className="flex items-center gap-0.5">
          <Tooltip>
            <TooltipTrigger
              render={
                <Link
                  href="/"
                  aria-label="New idea"
                  className={cn(buttonVariants({ variant: "ghost", size: "icon-sm" }))}
                />
              }
            >
              <SquarePen size={15} strokeWidth={2} />
            </TooltipTrigger>
            <TooltipContent>New idea</TooltipContent>
          </Tooltip>
          <RecentIdeas />
          <ThemeToggle />
          {/* The menu reads the URL (`?settings=`), so it streams in behind a boundary. */}
          <Suspense fallback={<Skeleton className="ml-1.5 size-6" />}>
            <AccountMenu />
          </Suspense>
        </div>
      </div>
    </header>
  );
}
