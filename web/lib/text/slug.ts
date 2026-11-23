const SLUG_LIMIT = 40;
const FALLBACK_SLUG = "idea";

/** A short file-name slug from an idea's title: lowercase letters and digits joined by single dashes. */
export function titleSlug(title: string): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, SLUG_LIMIT)
    .replace(/-+$/g, "");
  return slug || FALLBACK_SLUG;
}
