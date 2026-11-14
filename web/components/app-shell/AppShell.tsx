"use client";

import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { cn } from "@/lib/utils";
import { ReactNode } from "react";
import { useState } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div className="min-h-screen bg-background">
      {/* Mobile top bar */}
      <TopBar />

      {/* Desktop sidebar */}
      <Sidebar collapsed={collapsed} onCollapsedChange={setCollapsed} />

      {/* Main content area */}
      <main className={cn("min-h-screen transition-normal", collapsed ? "md:ml-[4.5rem]" : "md:ml-64")}>
        <div className="mx-auto w-full max-w-[1440px] px-5 pb-12 pt-20 sm:px-8 md:px-10 md:pt-10 lg:px-14">
          {children}
        </div>
      </main>
    </div>
  );
}
