"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("metis-theme");
    const useDark = saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", useDark);
    setDark(useDark);
  }, []);

  const toggleTheme = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("metis-theme", next ? "dark" : "light");
    setDark(next);
  };

  return (
    <Button variant="ghost" size={compact ? "icon" : "sm"} onClick={toggleTheme} aria-label={`Switch to ${dark ? "light" : "dark"} appearance`} title={`Switch to ${dark ? "light" : "dark"} appearance`}>
      {dark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
      {!compact && <span>{dark ? "Light appearance" : "Dark appearance"}</span>}
    </Button>
  );
}
