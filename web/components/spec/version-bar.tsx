"use client";

import { ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { relativeTime } from "@/lib/history/relative-time";
import type { SpecVersionSummary } from "@/lib/schemas/spec";
import { MIN_VERSIONS_TO_COMPARE, shownNumber, sourceLabel, versionLabel, type SpecView } from "@/lib/spec/view";

interface VersionBarProps {
  /** Newest first. Undefined while the list loads or failed: the bar then shows only the newest number. */
  versions: readonly SpecVersionSummary[] | undefined;
  latestNumber: number;
  confirmedNumber: number | null;
  view: SpecView;
  onPick: (number: number) => void;
  onToggleCompare: () => void;
}

function currentLabel(versions: readonly SpecVersionSummary[] | undefined, view: SpecView, latestNumber: number): string {
  if (view.mode === "compare") return "Compare versions";
  const number = shownNumber(view, latestNumber) ?? latestNumber;
  const found = versions?.find((version) => version.number === number);
  return found ? `${versionLabel(number)} · ${sourceLabel(found.source)} · ${relativeTime(found.created_at)}` : versionLabel(number);
}

/** The version menu and the Compare toggle at the top of the Spec pane (sample `.vbar`). */
export function VersionBar({ versions, latestNumber, confirmedNumber, view, onPick, onToggleCompare }: VersionBarProps) {
  const shown = shownNumber(view, latestNumber);
  const canCompare = latestNumber >= MIN_VERSIONS_TO_COMPARE;
  const label = currentLabel(versions, view, latestNumber);
  return (
    <div className="mb-3 flex items-center gap-1.5">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={<Button type="button" variant="outline" size="sm" aria-label={`Versions: ${label}`} className="min-w-0 justify-between" />}
        >
          <span className="truncate">{label}</span>
          <ChevronDown size={13} aria-hidden="true" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64 p-0.5">
          <DropdownMenuGroup>
            <DropdownMenuLabel>Versions</DropdownMenuLabel>
            <DropdownMenuRadioGroup value={shown === null ? "" : String(shown)} onValueChange={(value) => onPick(Number(value))}>
              {(versions ?? []).map((version) => (
                <DropdownMenuRadioItem key={version.id} value={String(version.number)}>
                  <span className="font-medium">{versionLabel(version.number)}</span>
                  <span className="text-muted-foreground">{sourceLabel(version.source)}</span>
                  <span className="text-muted-foreground">{relativeTime(version.created_at)}</span>
                  {version.number === confirmedNumber ? <span className="text-success">Confirmed</span> : null}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-pressed={view.mode === "compare"}
        disabled={!canCompare}
        title={canCompare ? undefined : "Needs two versions"}
        onClick={onToggleCompare}
      >
        Compare
        {canCompare ? null : <span className="sr-only"> (needs two versions)</span>}
      </Button>
    </div>
  );
}
