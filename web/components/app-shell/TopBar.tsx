"use client";

import { Menu, X, LayoutDashboard, Settings } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";
import { UserMenu } from "./UserMenu";
import Link from "next/link";
import { ThemeToggle } from "./ThemeToggle";

export function TopBar() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <header className="fixed left-0 right-0 top-0 z-50 h-16 border-b bg-background/90 backdrop-blur-xl md:hidden">
      <div className="flex h-full items-center justify-between px-3 sm:px-5">
        {/* Hamburger Menu */}
        <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open menu">
              {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
          </SheetTrigger>
          <SheetContent className="w-72 p-0 max-w-[280px]">
            <div className="flex h-full flex-col">
              <div className="flex h-16 items-center justify-between border-b px-5">
                <Link href="/ideas" className="text-title-2 font-semibold tracking-tight">
                  Metis
                </Link>
              </div>
              <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto p-4" aria-label="Main navigation">
                <Link
                  href="/ideas"
                  className="flex items-center gap-3 rounded-md px-3 py-2.5 text-body font-medium text-foreground-muted hover:bg-muted/50 hover:text-foreground"
                  onClick={() => setSidebarOpen(false)}
                >
                  <LayoutDashboard className="h-5 w-5" />
                  Ideas
                </Link>
                <Link
                  href="/settings"
                  className="flex items-center gap-3 rounded-md px-3 py-2.5 text-body font-medium text-foreground-muted hover:bg-muted/50 hover:text-foreground"
                  onClick={() => setSidebarOpen(false)}
                >
                  <Settings className="h-5 w-5" />
                  Settings
                </Link>
              </nav>
              <div className="shrink-0 space-y-3 border-t p-4">
                <WorkspaceSwitcher />
                <UserMenu />
                <ThemeToggle />
              </div>
            </div>
          </SheetContent>
        </Sheet>

        {/* Brand */}
        <Link href="/ideas" className="text-title-2 font-semibold tracking-tight">
          Metis
        </Link>

        {/* Workspace Switcher (mobile) */}
        <div className="hidden sm:flex">
          <WorkspaceSwitcher />
        </div>

        {/* User Menu (mobile) */}
        <div className="hidden sm:flex">
          <UserMenu />
        </div>
        <ThemeToggle compact />
      </div>
    </header>
  );
}

// Need to import LayoutDashboard and Settings for mobile nav
