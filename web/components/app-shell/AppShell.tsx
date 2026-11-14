"use client";

import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { cn } from "@/lib/utils";
import { ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      {/* Mobile top bar */}
      <TopBar />

      {/* Desktop sidebar */}
      <Sidebar />

      {/* Main content area */}
      <main
        className={cn(
          "min-h-screen transition-all duration-300",
          "md:ml-64 md:pl-0"
        )}
      >
        <div className="pt-16 md:pt-0 pb-8 px-4 md:px-8">
          {children}
        </div>
      </main>
    </div>
  );
}