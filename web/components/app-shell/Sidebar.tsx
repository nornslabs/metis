"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Settings,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";
import { UserMenu } from "./UserMenu";
import { ThemeToggle } from "./ThemeToggle";

const navigation = [
  { name: "Ideas", href: "/ideas", icon: LayoutDashboard },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar({ collapsed, onCollapsedChange }: { collapsed: boolean; onCollapsedChange: (collapsed: boolean) => void }) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 hidden h-screen border-r bg-sidebar transition-all duration-200 md:block",
        collapsed ? "w-[4.5rem]" : "w-64"
      )}
      aria-label="Main navigation"
    >
      <div className="flex h-full flex-col">
        {/* Logo/Brand */}
        <div
          className={cn(
            "flex h-16 items-center justify-between border-b px-4 transition-normal",
            collapsed && "justify-center"
          )}
        >
          {!collapsed && (
            <Link
              href="/ideas"
              className="truncate text-title-2 font-semibold tracking-tight"
              aria-label="Metis Home"
            >
              Metis
            </Link>
          )}
          <button
            onClick={() => onCollapsedChange(!collapsed)}
            className={cn(
              "rounded-md p-2 text-foreground-muted hover:bg-muted/50 hover:text-foreground transition-normal",
              collapsed && "mx-auto"
            )}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
          >
            {collapsed ? <ChevronRight className="h-5 w-5" /> : <ChevronLeft className="h-5 w-5" />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 p-3" aria-label="Main navigation">
          {navigation.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-callout font-medium transition-normal",
                  isActive
                    ? "bg-accent-bg text-accent"
                    : "text-foreground hover:bg-muted/50",
                  collapsed && "justify-center"
                )}
                title={collapsed ? item.name : undefined}
                aria-current={isActive ? "page" : undefined}
              >
                <item.icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
                {!collapsed && <span className="truncate">{item.name}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Workspace Switcher & User Menu */}
        <div className="space-y-3 border-t p-4 transition-normal">
          {!collapsed && <WorkspaceSwitcher />}
          {!collapsed && <UserMenu />}
          <ThemeToggle compact={collapsed} />
        </div>
      </div>
    </aside>
  );
}
