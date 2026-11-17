"use client";

import { X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

import { ACCOUNT_TRIGGER_ID } from "@/components/account/account-menu";
import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  SETTINGS_PARAM,
  SETTINGS_TABS,
  parseSettingsTab,
  withSettingsTab,
  type SettingsTab,
} from "@/lib/settings/tab";

import { AccountPanel } from "./account-panel";
import { IntegrationsPanel } from "./integrations-panel";
import { KeysPanel } from "./keys-panel";
import { PrefsPanel } from "./prefs-panel";

const TAB_LABELS: Readonly<Record<SettingsTab, string>> = {
  account: "Account",
  keys: "API keys",
  integrations: "Integrations",
  prefs: "Preferences",
};

const SHEET_CLASS =
  "gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:w-100 data-[side=right]:sm:max-w-100";

// Focus lands on the open tab, not the Close button: its tooltip would take the first Esc.
function focusSelectedTab(): HTMLElement | null {
  return document.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]');
}

/** Remembers the last focused element outside the sheet, so closing can hand focus back to it. */
function useReturnFocus() {
  const last = useRef<Element | null>(null);
  useEffect(() => {
    function remember(event: FocusEvent) {
      const target = event.target;
      if (target instanceof Element && !target.closest('[data-slot="sheet-content"]')) {
        last.current = target;
      }
    }
    document.addEventListener("focusin", remember);
    return () => document.removeEventListener("focusin", remember);
  }, []);
  // Menu items unmount when the menu closes; fall back to the account button that opened it.
  return () => {
    const remembered = last.current;
    return remembered instanceof HTMLElement && remembered.isConnected
      ? remembered
      : document.getElementById(ACCOUNT_TRIGGER_ID);
  };
}

/** Right-hand settings sheet, open while `?settings=<tab>` is on the URL. Not a page. */
export function SettingsSheet() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const tab = parseSettingsTab(search.get(SETTINGS_PARAM));
  const returnFocus = useReturnFocus();

  function go(next: SettingsTab | null) {
    router.replace(withSettingsTab(pathname, new URLSearchParams(search), next));
  }

  return (
    <Sheet open={tab !== null} onOpenChange={(open) => !open && go(null)}>
      <SheetContent
        showCloseButton={false}
        className={SHEET_CLASS}
        initialFocus={focusSelectedTab}
        finalFocus={returnFocus}
      >
        <div className="flex h-(--header-h) shrink-0 items-center justify-between border-b pr-2 pl-4">
          <SheetTitle className="text-body font-semibold">Settings</SheetTitle>
          <Tooltip>
            <TooltipTrigger
              render={
                <SheetClose
                  render={<Button variant="ghost" size="icon-sm" aria-label="Close settings" />}
                />
              }
            >
              <X size={15} />
            </TooltipTrigger>
            <TooltipContent>Close</TooltipContent>
          </Tooltip>
        </div>
        <Tabs
          value={tab ?? "account"}
          onValueChange={(value) => go(value as SettingsTab)}
          className="min-h-0 flex-1 gap-0"
        >
          <TabsList variant="line" className="h-auto w-full justify-start gap-0 border-b px-2">
            {SETTINGS_TABS.map((name) => (
              <TabsTrigger key={name} value={name} className="flex-none px-2.5 py-2 text-note">
                {TAB_LABELS[name]}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="account" className="flex min-h-0 flex-1 flex-col">
            <ScrollBody>
              <AccountPanel />
            </ScrollBody>
          </TabsContent>
          <TabsContent value="keys" className="flex min-h-0 flex-1 flex-col">
            <KeysPanel onClose={() => go(null)} />
          </TabsContent>
          <TabsContent value="integrations" className="flex min-h-0 flex-1 flex-col">
            <ScrollBody>
              <IntegrationsPanel />
            </ScrollBody>
          </TabsContent>
          <TabsContent value="prefs" className="flex min-h-0 flex-1 flex-col">
            <ScrollBody>
              <PrefsPanel />
            </ScrollBody>
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}

function ScrollBody({ children }: { children: React.ReactNode }) {
  return <div className="flex-1 overflow-y-auto p-4">{children}</div>;
}
