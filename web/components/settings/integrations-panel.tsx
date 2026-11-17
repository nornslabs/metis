import { SettingsGroup } from "./settings-field";

/** Placeholder until the Linear and Notion connect flows ship. */
export function IntegrationsPanel() {
  return (
    <SettingsGroup title="Planning tools" hint="Export plans to Linear and Notion.">
      <div className="flex items-center justify-between border p-2.5 text-control">
        <span>Linear and Notion</span>
        <span className="border px-1.5 text-meta text-muted-foreground">Soon</span>
      </div>
    </SettingsGroup>
  );
}
