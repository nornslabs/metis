import { ThemeSegment } from "@/components/account/theme-segment";

import { SettingsGroup } from "./settings-field";

export function PrefsPanel() {
  return (
    <SettingsGroup title="Appearance">
      <ThemeSegment />
    </SettingsGroup>
  );
}
