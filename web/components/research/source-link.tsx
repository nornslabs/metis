import { ExternalLink } from "lucide-react";

import { domainOf, safeHref } from "@/lib/research/view";

/** A source as a safe external link (domain as text); plain "No source" when the URL is not http(s). */
export function SourceLink({ url }: { url: string | null }) {
  const href = safeHref(url);
  const domain = domainOf(url);
  if (!href || !domain) return <span className="text-meta text-muted-foreground">No source</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="inline-flex items-center gap-1 font-mono text-meta text-muted-foreground underline underline-offset-2 hover:text-foreground"
    >
      {domain}
      <ExternalLink size={11} aria-hidden="true" />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}
