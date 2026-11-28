const COMPONENTS_HEADING = "## MVP components";
const SECTION_PREFIX = "## ";
const COMPONENT_PREFIX = "### ";

/** The component names in an HLD: the `###` headings under "MVP components" (`render_hld_markdown`). */
export function hldComponentNames(contentMd: string): string[] {
  const names: string[] = [];
  let inComponents = false;
  for (const line of contentMd.split("\n")) {
    if (line.startsWith(SECTION_PREFIX)) inComponents = line.trim() === COMPONENTS_HEADING;
    else if (inComponents && line.startsWith(COMPONENT_PREFIX)) {
      const name = line.slice(COMPONENT_PREFIX.length).trim();
      if (name !== "") names.push(name);
    }
  }
  return names;
}
