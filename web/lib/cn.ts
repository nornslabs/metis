import { createCn } from "cn/config";

// The custom lengths in app/globals.css (@theme). Without them the merger reads `text-meta` as a
// colour and drops the real colour class. Keep the lists in sync with that block.
export const cn = createCn({
  extend: {
    theme: {
      text: ["micro", "eyebrow", "meta", "note", "control", "body", "title", "score", "display"],
      tracking: ["eyebrow", "divider", "label", "score"],
      spacing: ["control", "badge", "track", "tick"],
      container: ["pitch", "headline", "lead", "card", "crumb", "crumb-narrow"],
    },
  },
});
